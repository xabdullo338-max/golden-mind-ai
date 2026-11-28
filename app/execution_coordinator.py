from __future__ import annotations

from dataclasses import dataclass
from .event_bus import EventBus, TradingEvent
from .execution_ledger import ExecutionLedger
from .journal import JournalOrder, TradingJournal
from .order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate
from .position_engine import PositionEngine

@dataclass
class ExecutionCoordinator:
    """Bridges broker updates to lifecycle, journal, positions and events."""

    lifecycle: OrderLifecycle
    journal: TradingJournal
    event_bus: EventBus
    positions: PositionEngine | None = None
    execution_ledger: ExecutionLedger | None = None
    _recovery_active: bool = False
    _deferred_updates: list[OrderUpdate] | None = None

    def __post_init__(self):
        if self.execution_ledger is None:
            self.execution_ledger = ExecutionLedger()
        self._deferred_updates = []

    def begin_recovery(self) -> None:
        self._recovery_active = True

    async def end_recovery(self) -> None:
        self._recovery_active = False
        deferred = list(self._deferred_updates or [])
        self._deferred_updates = []
        for update in deferred:
            await self.broker_update(update)

    async def submitted(self, account_id: str, broker: str, client_order_id: str,
                        symbol: str, side: str, quantity: float) -> None:
        self.journal.upsert_order(JournalOrder(
            client_order_id=client_order_id, account_id=account_id, broker=broker,
            symbol=symbol, side=side, quantity=quantity, status=OrderStatus.NEW.value,
        ))
        await self.event_bus.publish(TradingEvent.create(
            "ORDER_SUBMITTED", account_id, broker=broker,
            client_order_id=client_order_id, symbol=symbol, side=side, quantity=quantity,
        ))

    async def broker_update(self, update: OrderUpdate, *, allow_during_recovery: bool = False) -> OrderUpdate:
        if self._recovery_active and not allow_during_recovery:
            self._deferred_updates.append(update)
            existing = self.lifecycle.get(update.client_order_id, update.account_id, update.broker)
            return existing or update
        existing = self.lifecycle.get(
            update.client_order_id,
            update.account_id,
            update.broker,
        )
        # Exact replay of the same broker state is idempotent. Do not emit a
        # second execution event or touch journal/position state.
        if existing == update:
            return existing

        applied = self.lifecycle.apply(update)

        # A delayed/duplicate broker event can be rejected by the lifecycle
        # state machine. Do not re-journal or re-publish the already accepted
        # state as a fresh execution event.
        if applied != update:
            return applied

        delta = self.execution_ledger.delta(
            applied.client_order_id,
            applied.executed_quantity,
            account_id=applied.account_id,
            broker=applied.broker,
        )

        if (self.positions and delta > 0 and
                applied.status in {OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED} and
                applied.average_price is not None):
            saved = self.journal.get_order(applied.client_order_id, applied.account_id, applied.broker) or {}
            side = str(saved.get("side") or applied.side or "").upper()
            if side in {"BUY", "SELL"}:
                fill_price = applied.last_fill_price or applied.average_price
                # The execution ledger is authoritative for the new cumulative delta.
                # Binance also provides the last-fill quantity/price, which is more
                # accurate than applying the cumulative average price to the delta.
                if fill_price is not None:
                    self.positions.apply_fill(applied.account_id, applied.symbol, side,
                                               delta, fill_price)

        saved = self.journal.get_order(applied.client_order_id, applied.account_id, applied.broker) or {}
        self.journal.upsert_order(JournalOrder(
            client_order_id=applied.client_order_id,
            account_id=applied.account_id,
            broker=applied.broker,
            symbol=applied.symbol,
            side=str(saved.get("side") or applied.side or "UNKNOWN"),
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
            event_name, applied.account_id, broker=applied.broker,
            client_order_id=applied.client_order_id, symbol=applied.symbol,
            status=applied.status.value, executed_quantity=delta,
            cumulative_executed_quantity=applied.executed_quantity,
            average_price=applied.average_price,
            broker_order_id=applied.broker_order_id,
        ))
        return applied
