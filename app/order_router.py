from __future__ import annotations

import asyncio
from typing import Any, Callable

from .account_manager import AccountManager
from .idempotency import OrderIdempotencyGuard
from .kill_switch import KillSwitch
from .order_models import OrderRequest
from .execution_gate import ExecutionGate
from .portfolio_state import PortfolioStateManager
from .risk import AccountSnapshot, DailyLossGuard


class OrderRouter:
    def __init__(
        self,
        accounts: AccountManager,
        kill_switch: KillSwitch | None = None,
        idempotency: OrderIdempotencyGuard | None = None,
        execution_gate: ExecutionGate | None = None,
        portfolio_state: PortfolioStateManager | None = None,
        daily_loss_guard: DailyLossGuard | None = None,
        snapshot_provider: Callable[[str], AccountSnapshot | None] | None = None,
    ):
        self.accounts = accounts
        self.kill_switch = kill_switch or KillSwitch()
        self.idempotency = idempotency or OrderIdempotencyGuard()
        self.execution_gate = execution_gate
        self.portfolio_state = portfolio_state
        self.daily_loss_guard = daily_loss_guard or DailyLossGuard()
        self.snapshot_provider = snapshot_provider

    def _daily_loss_ok(self, account_id: str, *, live: bool) -> bool:
        # Simulated/testnet execution can proceed without a live account
        # snapshot. LIVE execution must have an actual risk snapshot.
        if not live:
            return True
        if self.snapshot_provider is None:
            return False
        snapshot = self.snapshot_provider(account_id)
        return snapshot is not None and self.daily_loss_guard.allowed(snapshot)

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
            live = managed.adapter.account.mode == "LIVE"
            self.execution_gate.assert_ready(
                account_enabled=managed.enabled,
                state_confirmed=confirmed,
                daily_loss_ok=self._daily_loss_ok(account_id, live=live),
                # LIVE remains explicitly disabled until a separate,
                # authenticated live-trading enablement mechanism is added.
                live_enabled=not live,
            )

        key = f"{account_id}:{order.client_order_id}"
        decision = self.idempotency.check_and_mark(key)
        if not decision.allowed:
            raise RuntimeError(decision.reason)

        try:
            return await self.accounts.order_to(account_id, order)
        except Exception:
            self.idempotency.forget(key)
            raise

    async def broadcast(self, order: OrderRequest) -> list[dict[str, Any]]:
        accounts = [a for a in self.accounts.list_accounts() if a["enabled"]]
        for account in accounts:
            self.kill_switch.assert_allowed(account["account_id"])
        tasks = [self.route(a["account_id"], order) for a in accounts]
        return await asyncio.gather(*tasks) if tasks else []
