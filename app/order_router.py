from __future__ import annotations

import asyncio
from typing import Any
from .account_manager import AccountManager
from .idempotency import OrderIdempotencyGuard
from .kill_switch import KillSwitch
from .order_models import OrderRequest
from .execution_gate import ExecutionGate
from .portfolio_state import PortfolioStateManager

class OrderRouter:
    def __init__(self, accounts: AccountManager, kill_switch: KillSwitch | None = None,
                 idempotency: OrderIdempotencyGuard | None = None,
                 execution_gate: ExecutionGate | None = None,
                 portfolio_state: PortfolioStateManager | None = None):
        self.accounts = accounts
        self.kill_switch = kill_switch or KillSwitch()
        self.idempotency = idempotency or OrderIdempotencyGuard()
        self.execution_gate = execution_gate
        self.portfolio_state = portfolio_state

    async def route(self, account_id: str, order: OrderRequest) -> dict[str, Any]:
        self.kill_switch.assert_allowed(account_id)
        managed = self.accounts.accounts.get(account_id)
        if managed is None:
            raise RuntimeError(f"Unknown account {account_id}")
        if self.execution_gate is not None:
            confirmed = (
                self.portfolio_state.is_confirmed(account_id)
                if self.portfolio_state is not None
                else False
            )
            self.execution_gate.assert_ready(
                account_enabled=managed.enabled,
                state_confirmed=confirmed,
                daily_loss_ok=True,
                live_enabled=managed.adapter.account.mode != "LIVE",
            )
        key = f"{account_id}:{order.client_order_id}"
        decision = self.idempotency.check_and_mark(key)
        if not decision.allowed:
            raise RuntimeError(decision.reason)
        try:
            return await self.accounts.order_to(account_id, order)
        except Exception:
            # Do not permanently consume an ID when the broker never accepted it.
            self.idempotency.forget(key)
            raise

    async def broadcast(self, order: OrderRequest) -> list[dict[str, Any]]:
        accounts = [a for a in self.accounts.list_accounts() if a["enabled"]]
        for account in accounts:
            self.kill_switch.assert_allowed(account["account_id"])
        tasks = [self.route(a["account_id"], order) for a in accounts]
        return await asyncio.gather(*tasks) if tasks else []
