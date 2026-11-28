from __future__ import annotations
from typing import Any
import httpx
from .base import BrokerAdapter, BrokerAccount

class IBKRAPIError(RuntimeError):
    pass

class IBKRAdapter(BrokerAdapter):
    """IBKR Client Portal adapter.

    PAPER: local simulation, no gateway call.
    DEMO: IBKR paper/demo gateway account.
    LIVE: real IBKR account.
    """

    def __init__(self, account_id: str, mode: str = "PAPER",
                 base_url: str = "https://localhost:5000",
                 session_cookie: str | None = None,
                 verify_tls: bool = True, timeout_seconds: float = 10.0):
        self.account = BrokerAccount(account_id, "IBKR", mode)
        self.base_url = base_url.rstrip("/")
        self.session_cookie = session_cookie
        self.verify_tls = verify_tls
        self.timeout_seconds = timeout_seconds
        self._paper_cash = 300.0

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.session_cookie:
            headers["Cookie"] = f"api={self.session_cookie}"
        return headers

    async def _request(self, method: str, path: str, *, json: Any = None):
        async with httpx.AsyncClient(timeout=self.timeout_seconds, verify=self.verify_tls) as client:
            response = await client.request(method, f"{self.base_url}{path}",
                                             headers=self._headers(), json=json)
        if response.status_code >= 400:
            raise IBKRAPIError(f"IBKR API {response.status_code}: {response.text[:500]}")
        return response.json()

    def _gateway_mode(self) -> bool:
        return self.account.mode in {"DEMO", "LIVE"}

    async def auth_status(self) -> dict[str, Any]:
        if not self._gateway_mode():
            return {"authenticated": True, "mode": "PAPER"}
        return await self._request("GET", "/v1/api/iserver/auth/status")

    async def get_balance(self) -> dict[str, float]:
        if self.account.mode == "PAPER":
            return {"USD": self._paper_cash}
        result = await self._request("GET", "/v1/api/iserver/account/summary")
        values: dict[str, float] = {}
        for key in ("NetLiquidation", "TotalCashValue", "BuyingPower"):
            item = result.get(key)
            if isinstance(item, dict) and item.get("value") is not None:
                try:
                    values[key] = float(item["value"])
                except (TypeError, ValueError):
                    pass
        return values

    async def get_positions(self) -> list[dict[str, Any]]:
        if self.account.mode == "PAPER":
            return []
        raw = await self._request(
            "GET",
            f"/v1/api/portfolio/{self.account.account_id}/positions/0",
        )
        normalized: list[dict[str, Any]] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                quantity = float(item.get("position", item.get("quantity", 0.0)) or 0.0)
            except (TypeError, ValueError):
                continue
            symbol = str(item.get("symbol") or "").upper().strip()
            if not symbol or quantity == 0:
                continue
            asset = symbol
            normalized.append({
                "asset": asset,
                "quantity": quantity,
                "symbol": symbol,
                "avgPrice": float(item.get("avgPrice", item.get("averagePrice", 0.0)) or 0.0),
                "conid": item.get("conid"),
            })
        return normalized

    async def hydrate_positions(self, position_engine: Any, account_id: str,
                                positions: list[dict[str, Any]]) -> bool:
        """Hydrate IBKR positions from broker-reported authoritative quantities.

        IBKR equity positions are not Binance-style asset/USDT spot positions, so
        recovery must not attempt to reconstruct them through Binance trade history.
        Negative quantities are rejected because the current PositionEngine is
        explicitly long-only.
        """
        for position in positions:
            symbol = str(position.get("symbol") or position.get("asset") or "").upper().strip()
            try:
                quantity = float(position.get("quantity", 0.0) or 0.0)
                average_entry = float(
                    position.get("avgPrice", position.get("averagePrice", 0.0)) or 0.0
                )
            except (TypeError, ValueError):
                return False
            if not symbol or quantity < 0 or (quantity > 0 and average_entry <= 0):
                return False

        position_engine.clear_account(account_id)
        for position in positions:
            symbol = str(position.get("symbol") or position.get("asset") or "").upper().strip()
            quantity = float(position.get("quantity", 0.0) or 0.0)
            average_entry = float(
                position.get("avgPrice", position.get("averagePrice", 0.0)) or 0.0
            )
            if quantity > 0:
                position_engine.hydrate(account_id, symbol, quantity, average_entry)
        return True

    @staticmethod
    def _normalize_order(item: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        symbol = str(item.get("symbol") or item.get("ticker") or "").upper().strip()
        side = str(item.get("side") or item.get("action") or "").upper().strip()
        status = IBKRAdapter._map_order_status(item.get("status"))
        client_order_id = str(
            item.get("clientOrderId")
            or item.get("client_order_id")
            or item.get("orderRef")
            or item.get("order_ref")
            or ""
        ).strip()
        broker_order_id = item.get("orderId", item.get("order_id"))
        if not symbol or side not in {"BUY", "SELL"} or not client_order_id:
            return None
        try:
            original = float(
                item.get("quantity", item.get("origQty", item.get("totalQuantity", 0.0))) or 0.0
            )
            executed = float(
                item.get("executedQty", item.get("filledQuantity", item.get("cumQty", 0.0))) or 0.0
            )
        except (TypeError, ValueError):
            return None
        if original <= 0 or executed < 0 or executed > original + 1e-10:
            return None
        price_value = item.get("avgPrice", item.get("averagePrice", item.get("price")))
        try:
            avg_price = float(price_value) if price_value not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            avg_price = None
        return {
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "side": side,
            "status": status or "NEW",
            "origQty": original,
            "executedQty": executed,
            "avgPrice": avg_price,
            "orderId": str(broker_order_id) if broker_order_id is not None else None,
        }

    @staticmethod
    def _map_order_status(status: str) -> str:
        value = str(status or "").strip().upper().replace(" ", "")
        return {
            "SUBMITTED": "NEW",
            "PRESUBMITTED": "NEW",
            "PENDING": "NEW",
            "PENDING_SUBMIT": "NEW",
            "PARTIALLYFILLED": "PARTIALLY_FILLED",
            "PARTIALFILLED": "PARTIALLY_FILLED",
            "FILLED": "FILLED",
            "CANCELLED": "CANCELED",
            "CANCELED": "CANCELED",
            "EXPIRED": "EXPIRED",
            "INACTIVE": "UNKNOWN",
            "REJECTED": "REJECTED",
        }.get(value, "UNKNOWN")

    async def get_open_orders(self) -> list[dict[str, Any]]:
        if self.account.mode == "PAPER":
            return []
        raw = await self._request("GET", "/v1/api/iserver/account/orders")
        items = raw.get("orders", []) if isinstance(raw, dict) else raw
        normalized: list[dict[str, Any]] = []
        for item in items if isinstance(items, list) else []:
            order = self._normalize_order(item)
            if order is not None:
                normalized.append(order)
        return normalized

    async def get_order_by_client_id(self, symbol: str, client_order_id: str) -> dict[str, Any] | None:
        if self.account.mode == "PAPER":
            return None
        for order in await self.get_open_orders():
            if (
                order.get("clientOrderId") == client_order_id
                and str(order.get("symbol", "")).upper() == symbol.upper()
            ):
                return order
        return None

    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "MARKET", **kwargs: Any):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.account.mode == "PAPER":
            return {"status": "FILLED", "broker": "IBKR", "mode": "PAPER",
                    "account_id": self.account.account_id, "symbol": symbol,
                    "side": side.upper(), "quantity": quantity,
                    "clientOrderId": kwargs.get("client_order_id")}
        if not self.session_cookie:
            raise IBKRAPIError("IBKR session cookie is required for DEMO/LIVE execution")
        order = {"acctId": self.account.account_id, "conid": kwargs.get("conid"),
                 "symbol": symbol, "side": side.upper(), "quantity": quantity,
                 "tif": kwargs.get("tif", "DAY"), "type": order_type.upper()}
        if order["conid"] is None:
            raise ValueError("IBKR order requires conid from contract lookup")
        if order["type"] == "LMT":
            if kwargs.get("limit_price") is None:
                raise ValueError("limit_price is required for LMT orders")
            order["price"] = kwargs["limit_price"]
        return await self._request("POST", f"/v1/api/iserver/account/{self.account.account_id}/orders",
                                   json={"orders": [order]})

    async def cancel_order(self, symbol: str, order_id: str):
        if self.account.mode == "PAPER":
            return {"status": "CANCELED", "broker": "IBKR", "mode": "PAPER",
                    "symbol": symbol, "order_id": order_id}
        if not self.session_cookie:
            raise IBKRAPIError("IBKR session cookie is required")
        return await self._request("DELETE",
                                   f"/v1/api/iserver/account/{self.account.account_id}/order/{order_id}")
