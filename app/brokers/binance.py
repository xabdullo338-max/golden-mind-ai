from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import urlencode
import httpx
from .base import BrokerAdapter, BrokerAccount
from ..market_data import MarketTick
from datetime import datetime, timezone

class BinanceAPIError(RuntimeError):
    pass

class BinanceAdapter(BrokerAdapter):
    """Binance Spot adapter: PAPER simulation, TESTNET/DEMO sandbox, LIVE real account."""

    def __init__(self, account_id: str, api_key: str = "", api_secret: str = "",
                 base_url: str = "https://testnet.binance.vision", mode: str = "PAPER",
                 initial_quote_balance: float = 300.0, timeout_seconds: float = 10.0,
                 reconciliation_symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")):
        self.account = BrokerAccount(account_id, "BINANCE", mode)
        self.api_key, self.api_secret = api_key, api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.reconciliation_symbols = tuple(s.upper() for s in reconciliation_symbols if s.strip())
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
        url = f"{self.base_url}{path}"
        if signed:
            url += "?" + self._signed_query(params)
        else:
            query = urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url += "?" + query
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
        return int((await self._request("GET", "/api/v3/time"))["serverTime"])

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
            return [{"asset": s.removesuffix("USDT"), "quantity": q}
                    for s, q in self._paper_positions.items() if q > 0]
        balances = await self.get_balance()
        return [{"asset": a, "quantity": q} for a, q in balances.items()
                if a not in {"USDT", "USDC", "BUSD"}]

    async def get_market_tick(self, symbol: str) -> MarketTick | None:
        symbol = symbol.upper()
        if self.account.mode == "PAPER":
            meta = next(
                (o.get("metadata", {}) for o in self._paper_orders.values()
                 if str(o.get("symbol", "")).upper() == symbol),
                {},
            )
            price = float(meta.get("price") or 0)
            if price <= 0:
                return None
            return MarketTick("BINANCE", symbol, price, datetime.now(timezone.utc))
        if not self.api_key:
            return None
        data = await self._request(
            "GET", "/api/v3/ticker/24hr", params={"symbol": symbol}
        )
        return MarketTick(
            "BINANCE",
            symbol,
            float(data["lastPrice"]),
            datetime.now(timezone.utc),
            bid=float(data["bidPrice"]),
            ask=float(data["askPrice"]),
            volume=float(data["volume"]),
        )

    async def get_trade_history(self, symbol: str, limit: int = 1000) -> list[dict[str, Any]]:
        if self.account.mode == "PAPER":
            return [
                {"symbol": order.get("symbol", symbol), "side": order.get("side"),
                 "qty": order.get("executedQty", 0), "price": order.get("price", 0),
                 "commission": 0, "commissionAsset": "USDT",
                 "time": int(time.time() * 1000), "orderId": order.get("orderId"),
                 "id": order.get("orderId")}
                for order in self._paper_orders.values()
                if str(order.get("symbol", "")).upper() == symbol.upper()
                and order.get("status") == "FILLED"
            ]
        if not self._execution_allowed():
            raise BinanceAPIError("Execution is disabled for this account mode")
        return await self._request(
            "GET", "/api/v3/myTrades", signed=True,
            params={"symbol": symbol.upper(), "limit": max(1, min(int(limit), 1000))},
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if self.account.mode == "PAPER":
            orders = [o for o in self._paper_orders.values()
                      if o.get("status") not in {"FILLED", "CANCELED"}]
            if symbol:
                return [o for o in orders if str(o.get("symbol", "")).upper() == symbol.upper()]
            return orders

        symbols = (symbol.upper(),) if symbol else self.reconciliation_symbols
        if not symbols:
            raise BinanceAPIError("At least one reconciliation symbol is required")

        results: list[dict[str, Any]] = []
        for item in symbols:
            orders = await self._request(
                "GET", "/api/v3/openOrders", signed=True, params={"symbol": item}
            )
            results.extend(orders)
        return results

    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "MARKET", **kwargs: Any):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        symbol, side, order_type = symbol.upper(), side.upper(), order_type.upper()
        client_id = kwargs.get("client_order_id")

        if self.account.mode == "PAPER":
            meta = kwargs.get("metadata") or {}
            price = float(kwargs.get("price") or kwargs.get("limit_price") or meta.get("price") or 0)
            if price <= 0:
                raise ValueError("PAPER order requires current price")
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
        params = {"symbol": symbol, "side": side, "type": order_type, "quantity": quantity}
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
