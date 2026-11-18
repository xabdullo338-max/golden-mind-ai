from __future__ import annotations

from typing import Any

import httpx

from .base import BrokerAdapter, BrokerAccount


class IBKRAPIError(RuntimeError):
    pass


class IBKRAdapter(BrokerAdapter):
    """IBKR Client Portal Web API adapter.

    The Client Portal Gateway is expected to run separately and expose the
    authenticated REST API. This adapter does not store an IBKR password.
    PAPER mode never sends orders.
    """

    def __init__(self, account_id: str, mode: str = "PAPER",
                 base_url: str = "https://localhost:5000",
                 session_cookie: str | None = None,
                 verify_tls: bool = True, timeout_seconds: float = 10.0):
        self.account = BrokerAccount(account_id, "IBKR", mode.upper())
        self.base_url = base_url.rstrip("/")
        self.session_cookie = session_cookie
        self.verify_tls = verify_tls
        self.timeout_seconds = timeout_seconds

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

    async def auth_status(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/api/iserver/auth/status")

    async def get_balance(self) -> dict[str, float]:
        if self.account.mode == "PAPER":
            return {"USD": 0.0}
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
        return await self._request("GET", f"/v1/api/portfolio/{self.account.account_id}/positions/0")

    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "MARKET", **kwargs: Any):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.account.mode == "PAPER":
            return {"status": "PAPER", "broker": "IBKR",
                    "account_id": self.account.account_id, "symbol": symbol,
                    "side": side, "quantity": quantity}
        if not self.session_cookie:
            raise IBKRAPIError("IBKR session cookie is required for live/test execution")
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
            return {"status": "PAPER", "broker": "IBKR", "symbol": symbol, "order_id": order_id}
        if not self.session_cookie:
            raise IBKRAPIError("IBKR session cookie is required")
        return await self._request("DELETE",
                                   f"/v1/api/iserver/account/{self.account.account_id}/order/{order_id}")