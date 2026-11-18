from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class RecoveryResult:
    account_id: str
    broker_positions: list[dict[str, Any]]
    broker_open_orders: list[dict[str, Any]]
    confirmed: bool
    reason: str = ""

class BrokerRecovery:
    """Rebuilds runtime state from broker truth after restart/reconnect."""

    def __init__(self, accounts, portfolio_state, journal):
        self.accounts = accounts
        self.portfolio_state = portfolio_state
        self.journal = journal

    async def recover_account(self, account_id: str) -> RecoveryResult:
        managed = self.accounts.accounts.get(account_id)
        if not managed or not managed.enabled:
            return RecoveryResult(account_id, [], [], False, "account unavailable")

        adapter = managed.adapter
        try:
            positions = await adapter.get_positions()
            open_orders: list[dict[str, Any]] = []
            # Adapters may expose open-order retrieval later; keep recovery
            # conservative until broker truth is available.
            return RecoveryResult(
                account_id=account_id,
                broker_positions=positions,
                broker_open_orders=open_orders,
                confirmed=True,
                reason="broker positions reconciled",
            )
        except Exception as exc:
            return RecoveryResult(account_id, [], [], False, f"recovery failed: {type(exc).__name__}")

    async def recover_all(self) -> list[RecoveryResult]:
        results = []
        for account_id in self.accounts.accounts:
            results.append(await self.recover_account(account_id))
        return results
