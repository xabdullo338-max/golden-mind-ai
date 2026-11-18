from __future__ import annotations

from typing import Any
from .binance_events import execution_report_to_update
from .execution_coordinator import ExecutionCoordinator


class BinanceExecutionBridge:
    """Routes Binance user-data order events into the broker-neutral execution coordinator."""

    def __init__(self, account_id: str, coordinator: ExecutionCoordinator):
        self.account_id = account_id
        self.coordinator = coordinator

    async def handle(self, message: dict[str, Any]) -> None:
        event = message.get("event")
        payload = event if isinstance(event, dict) else message
        update = execution_report_to_update(payload, self.account_id)
        if update is not None:
            await self.coordinator.broker_update(update)
