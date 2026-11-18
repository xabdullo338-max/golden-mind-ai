from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .event_bus import EventBus, TradingEvent
from .journal import JournalOrder, TradingJournal
from .order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate

@dataclass
class ExecutionCoordinator:
    """Bridges broker updates to lifecycle, journal and realtime events."""

    lifecycle: OrderLifecycle
    journal: TradingJournal
    event_bus: EventBus

    async def submitted(
        self,
        account_id: str,
        broker: str,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: float,
    ) -> None:
        self.journal.upsert_order(JournalOrder(
            client_order_id=client_order_id,
            account_id=account_id,
            broker=broker,
            symbol=symbol,
            side=side,
            quantity=quantity,
            status=OrderStatus.NEW.value,
        ))
        await self.event_bus.publish(TradingEvent.create(
            "ORDER_SUBMITTED",
            account_id,
            broker=broker,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
        ))

    async def broker_update(self, update: OrderUpdate) -> OrderUpdate:
        applied = self.lifecycle.apply(update)
        self.journal.upsert_order(JournalOrder(
            client_order_id=applied.client_order_id,
            account_id=applied.account_id,
            broker=applied.broker,
            symbol=applied.symbol,
            side="UNKNOWN",
            quantity=applied.executed_quantity,
            status=applied.status.value,
            broker_order_id=applied.broker_order_id,
        ))
        event_name = {
            OrderStatus.FILLED: "ORDER_FILLED",
            OrderStatus.PARTIALLY_FILLED: "ORDER_PARTIALLY_FILLED",
            OrderStatus.CANCELED: "ORDER_CANCELED",
            OrderStatus.REJECTED: "ORDER_REJECTED",
            OrderStatus.EXPIRED: "ORDER_EXPIRED",
        }.get(applied.status, "ORDER_UPDATE")
        await self.event_bus.publish(TradingEvent.create(
            event_name,
            applied.account_id,
            broker=applied.broker,
            client_order_id=applied.client_order_id,
            symbol=applied.symbol,
            status=applied.status.value,
            executed_quantity=applied.executed_quantity,
            average_price=applied.average_price,
            broker_order_id=applied.broker_order_id,
        ))
        return applied
