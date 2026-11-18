from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .base import BrokerAdapter, BrokerAccount


class BinanceAPIError(RuntimeError):
    pass


class BinanceAdapter(BrokerAdapter):
    """Binance Spot adapter with PAPER, TESTNET and guarded LIVE modes."""

    def __init__(self, account_id: str, api_key: str, api_secret: str,
                 base_url: str = "https://testnet.binance.vision",
                 mode: str = "PAPER", timeout_seconds: float = 10.0):
        self.account = BrokerAccount(account_id, "BINANCE", mode.upper())
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _signed_query(self, params: dict[str, Any]) -> str:
        clean = {k: v for k, v in params.items() if v is not None}
        clean.setdefault("timestamp", int(time.time() * 1000))
        clean.setdefault("recvWindow", 5000)
        query = urlencode(clean, doseq=True)
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    async def _request(self, method: str, path: str, *, signed: bool = False,
                       params: dict[str, Any] | None = None):
        params = params or {}
        headers = {"X-MBX-APIKEY": self.api_key}
        if signed:
            url = f"{self.base_url}{path}?{self._signed_query(params)}"
        else:
            query = urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.request(method, url, headers=headers)
        if response.status_code >= 400:
            raise BinanceAPIError(f"Binance API {response.status_code}: {response.text[:500]}")
        return response.json()

    def _execution_allowed(self) -> bool:
        if self.account.mode == "TESTNET":
            return True
        if self.account.mode == "LIVE":
            return os.getenv("GMAI_LIVE_TRADING", "false").lower() in {"1", "true", "yes"}
        return False

    async def ping(self) -> bool:
        await self._request("GET", "/api/v3/ping")
        return True

    async def get_server_time(self) -> int:
        result = await self._request("GET", "/api/v3/time")
        return int(result["serverTime"])

    async def get_balance(self) -> dict[str, float]:
        if self.account.mode == "PAPER":
            return {"USDT": 0.0}
        result = await self._request("GET", "/api/v3/account", signed=True)
        return {item["asset"]: float(item["free"]) + float(item["locked"])
                for item in result.get("balances", [])
                if float(item["free"]) + float(item["locked"]) > 0}

    async def get_positions(self) -> list[dict[str, Any]]:
        balances = await self.get_balance()
        return [{"asset": asset, "quantity": quantity} for asset, quantity in balances.items()
                if asset not in {"USDT", "USDC", "BUSD"}]

    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "MARKET", **kwargs: Any):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if not self._execution_allowed():
            return {"status": "PAPER", "broker": "BINANCE",
                    "account_id": self.account.account_id, "symbol": symbol,
                    "side": side, "quantity": quantity}
        params: dict[str, Any] = {"symbol": symbol.upper(), "side": side.upper(),
                                  "type": order_type.upper(), "quantity": quantity}
        if kwargs.get("client_order_id"):
            params["newClientOrderId"] = kwargs["client_order_id"]
        if params["type"] == "LIMIT":
            if kwargs.get("limit_price") is None:
                raise ValueError("limit_price is required for LIMIT orders")
            params["timeInForce"] = kwargs.get("time_in_force", "GTC")
            params["price"] = kwargs["limit_price"]
        return await self._request("POST", "/api/v3/order", signed=True, params=params)

    async def cancel_order(self, symbol: str, order_id: str):
        if not self._execution_allowed():
            return {"status": "PAPER", "broker": "BINANCE", "symbol": symbol, "order_id": order_id}
        return await self._request("DELETE", "/api/v3/order", signed=True,
                                   params={"symbol": symbol.upper(), "orderId": order_id})