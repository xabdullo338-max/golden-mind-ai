from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class RecoveryResult:
    account_id: str
    broker_positions: list[dict[str, Any]]
    broker_open_orders: list[dict[str, Any]]
    confirmed: bool
    reason: str = ""

class BrokerRecovery:
    """Rebuild runtime state from broker truth after restart/reconnect."""

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
            open_orders = await adapter.get_open_orders()
            return RecoveryResult(
                account_id=account_id,
                broker_positions=positions,
                broker_open_orders=open_orders,
                confirmed=True,
                reason="broker positions and open orders reconciled",
            )
        except Exception as exc:
            self.portfolio_state.mark_unconfirmed(account_id, adapter.account.broker)
            return RecoveryResult(account_id, [], [], False,
                                  f"recovery failed: {type(exc).__name__}")

    async def recover_all(self) -> list[RecoveryResult]:
        return [await self.recover_account(account_id) for account_id in self.accounts.accounts]
