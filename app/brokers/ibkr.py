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

    async def get_open_orders(self) -> list[dict[str, Any]]:
        if self.account.mode == "PAPER":
            return []
        return await self._request("GET", "/v1/api/iserver/account/orders")

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
