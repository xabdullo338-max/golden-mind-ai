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
    """Binance Spot adapter.

    PAPER: local simulation with an in-memory cash/position ledger.
    TESTNET/DEMO: Binance sandbox endpoint.
    LIVE: real Binance Spot account; requires GMAI_LIVE_TRADING=true.
    """

    def __init__(self, account_id: str, api_key: str = "", api_secret: str = "",
                 base_url: str = "https://testnet.binance.vision",
                 mode: str = "PAPER", initial_quote_balance: float = 300.0,
                 timeout_seconds: float = 10.0):
        self.account = BrokerAccount(account_id, "BINANCE", mode)
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._paper_cash = float(initial_quote_balance)
        self._paper_positions: dict[str, float] = {}
        self._paper_orders: dict[str, dict[str, Any]] = {}

    def _signed_query(self, params: dict[str, Any]) -> str:
        if not self.api_secret:
            raise BinanceAPIError("API secret is required for authenticated Binance mode")
        clean = {k: v for k, v in params.items() if v is not None}
        clean.setdefault("timestamp", int(time.time() * 1000))
        clean.setdefault("recvWindow", 5000)
        query = urlencode(clean, doseq=True)
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    async def _request(self, method: str, path: str, *, signed: bool = False,
                       params: dict[str, Any] | None = None):
        if not self.api_key:
            raise BinanceAPIError("API key is required for Binance broker mode")
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
        if self.account.mode in {"TESTNET", "DEMO"}:
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
            result = {"USDT": self._paper_cash}
            for symbol, qty in self._paper_positions.items():
                if qty > 0:
                    result[symbol.removesuffix("USDT")] = qty
            return result
        result = await self._request("GET", "/api/v3/account", signed=True)
        return {item["asset"]: float(item["free"]) + float(item["locked"])
                for item in result.get("balances", [])
                if float(item["free"]) + float(item["locked"]) > 0}

    async def get_positions(self) -> list[dict[str, Any]]:
        if self.account.mode == "PAPER":
            return [{"asset": asset.removesuffix("USDT"), "quantity": qty}
                    for asset, qty in self._paper_positions.items() if qty > 0]
        balances = await self.get_balance()
        return [{"asset": asset, "quantity": quantity} for asset, quantity in balances.items()
                if asset not in {"USDT", "USDC", "BUSD"}]

    async def get_open_orders(self) -> list[dict[str, Any]]:
        if self.account.mode == "PAPER":
            return list(self._paper_orders.values())
        # Binance requires symbol for this endpoint; caller can reconcile per symbol.
        return []

    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "MARKET", **kwargs: Any):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        symbol = symbol.upper()
        side = side.upper()
        order_type = order_type.upper()
        client_id = kwargs.get("client_order_id")

        if self.account.mode == "PAPER":
            price = float(kwargs.get("price") or kwargs.get("limit_price") or 0)
            if price <= 0:
                raise ValueError("PAPER order requires current price via price/limit_price")
            base = symbol.removesuffix("USDT")
            if side == "BUY":
                cost = quantity * price
                if cost > self._paper_cash:
                    raise BinanceAPIError("Insufficient PAPER balance")
                self._paper_cash -= cost
                self._paper_positions[base + "USDT"] = self._paper_positions.get(base + "USDT", 0.0) + quantity
            elif side == "SELL":
                held = self._paper_positions.get(base + "USDT", 0.0)
                if quantity > held + 1e-12:
                    raise BinanceAPIError("Insufficient PAPER position")
                self._paper_positions[base + "USDT"] = held - quantity
                self._paper_cash += quantity * price
            else:
                raise ValueError("side must be BUY or SELL")
            oid = client_id or f"PAPER-{int(time.time()*1000)}"
            result = {"status": "FILLED", "broker": "BINANCE", "mode": "PAPER",
                      "account_id": self.account.account_id, "symbol": symbol,
                      "side": side, "executedQty": quantity, "price": price,
                      "clientOrderId": oid, "orderId": oid}
            self._paper_orders[oid] = result
            return result

        if not self._execution_allowed():
            raise BinanceAPIError("Execution is disabled for this account mode")
        params: dict[str, Any] = {"symbol": symbol, "side": side, "type": order_type,
                                  "quantity": quantity}
        if client_id:
            params["newClientOrderId"] = client_id
        if order_type == "LIMIT":
            if kwargs.get("limit_price") is None:
                raise ValueError("limit_price is required for LIMIT orders")
            params["timeInForce"] = kwargs.get("time_in_force", "GTC")
            params["price"] = kwargs["limit_price"]
        return await self._request("POST", "/api/v3/order", signed=True, params=params)

    async def cancel_order(self, symbol: str, order_id: str):
        if self.account.mode == "PAPER":
            order = self._paper_orders.get(order_id)
            if order:
                order["status"] = "CANCELED"
            return {"status": "CANCELED", "broker": "BINANCE", "mode": "PAPER",
                    "symbol": symbol, "order_id": order_id}
        if not self._execution_allowed():
            raise BinanceAPIError("Execution is disabled")
        return await self._request("DELETE", "/api/v3/order", signed=True,
                                   params={"symbol": symbol.upper(), "orderId": order_id})
