from __future__ import annotations

from typing import Any

from .binance_events import execution_report_to_update
from .execution_coordinator import ExecutionCoordinator
from .portfolio_state import PortfolioStateManager
from .recovery import BrokerRecovery


class BinanceExecutionBridge:
    """Routes Binance user-data events and connection state into execution safety."""

    def __init__(
        self,
        account_id: str,
        coordinator: ExecutionCoordinator,
        portfolio_state: PortfolioStateManager | None = None,
        recovery: BrokerRecovery | None = None,
    ):
        self.account_id = account_id
        self.coordinator = coordinator
        self.portfolio_state = portfolio_state
        self.recovery = recovery

    def mark_disconnected(self) -> None:
        if self.portfolio_state is not None:
            broker = "BINANCE"
            self.portfolio_state.mark_unconfirmed(self.account_id, broker)

    async def mark_reconnected_and_recover(self) -> bool:
        if self.recovery is None:
            return False
        result = await self.recovery.recover_account(self.account_id)
        return result.confirmed

    async def handle(self, message: dict[str, Any]) -> None:
        event = message.get("event")
        payload = event if isinstance(event, dict) else message
        update = execution_report_to_update(payload, self.account_id)
        if update is not None:
            await self.coordinator.broker_update(update)
