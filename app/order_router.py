from __future__ import annotations

import asyncio
from typing import Any
from .account_manager import AccountManager
from .idempotency import OrderIdempotencyGuard
from .kill_switch import KillSwitch
from .order_models import OrderRequest

class OrderRouter:
    def __init__(self, accounts: AccountManager, kill_switch: KillSwitch | None = None,
                 idempotency: OrderIdempotencyGuard | None = None):
        self.accounts = accounts
        self.kill_switch = kill_switch or KillSwitch()
        self.idempotency = idempotency or OrderIdempotencyGuard()

    async def route(self, account_id: str, order: OrderRequest) -> dict[str, Any]:
        self.kill_switch.assert_allowed(account_id)
        self.idempotency.check_and_mark(f"{account_id}:{order.client_order_id}")
        try:
            return await self.accounts.order_to(account_id, order)
        except Exception:
            # Do not permanently consume an ID when the broker never accepted it.
            self.idempotency.forget(f"{account_id}:{order.client_order_id}")
            raise

    async def broadcast(self, order: OrderRequest) -> list[dict[str, Any]]:
        accounts = [a for a in self.accounts.list_accounts() if a["enabled"]]
        for account in accounts:
            self.kill_switch.assert_allowed(account["account_id"])
        tasks = [self.route(a["account_id"], order) for a in accounts]
        return await asyncio.gather(*tasks) if tasks else []
