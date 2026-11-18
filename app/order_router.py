from __future__ import annotations

import asyncio
from typing import Any

from .account_manager import AccountManager
from .kill_switch import KillSwitch
from .order_models import OrderRequest


class OrderRouter:
    def __init__(self, accounts: AccountManager, kill_switch: KillSwitch | None = None):
        self.accounts = accounts
        self.kill_switch = kill_switch or KillSwitch()

    async def route(self, account_id: str, order: OrderRequest) -> dict[str, Any]:
        self.kill_switch.assert_allowed(account_id)
        return await self.accounts.order_to(account_id, order)

    async def broadcast(self, order: OrderRequest) -> list[dict[str, Any]]:
        results = []
        for account in self.accounts.list_accounts():
            if account["enabled"]:
                self.kill_switch.assert_allowed(account["account_id"])
        tasks = [self.route(a["account_id"], order) for a in self.accounts.list_accounts() if a["enabled"]]
        if tasks:
            results = await asyncio.gather(*tasks)
        return results