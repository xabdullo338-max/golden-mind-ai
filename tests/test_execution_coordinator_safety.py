import pytest

from app.event_bus import EventBus
from app.execution_coordinator import ExecutionCoordinator
from app.execution_ledger import ExecutionLedger
from app.journal import TradingJournal
from app.order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate
from app.position_engine import PositionEngine


def update(status, qty, price, last_qty=None, client="coord-1"):
    return OrderUpdate(
        broker="BINANCE",
        account_id="A",
        client_order_id=client,
        status=status,
        symbol="BTCUSDT",
        executed_quantity=qty,
        average_price=price,
        last_fill_quantity=last_qty,
        last_fill_price=price if last_qty else None,
        original_quantity=1.0,
        side="BUY",
    )


@pytest.mark.asyncio
async def test_stale_partial_fill_does_not_double_apply_position():
    positions = PositionEngine()
    coordinator = ExecutionCoordinator(
        OrderLifecycle(),
        TradingJournal(":memory:"),
        EventBus(),
        positions=positions,
        execution_ledger=ExecutionLedger(),
    )

    await coordinator.broker_update(
        update(OrderStatus.PARTIALLY_FILLED, 0.4, 100.0, last_qty=0.4)
    )
    await coordinator.broker_update(
        update(OrderStatus.PARTIALLY_FILLED, 0.2, 99.0, last_qty=0.2)
    )

    position = positions.get("A", "BTCUSDT")
    assert position.quantity == pytest.approx(0.4)
    assert position.average_entry == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_incremental_partial_fills_and_final_fill_apply_only_deltas():
    positions = PositionEngine()
    coordinator = ExecutionCoordinator(
        OrderLifecycle(),
        TradingJournal(":memory:"),
        EventBus(),
        positions=positions,
        execution_ledger=ExecutionLedger(),
    )

    await coordinator.broker_update(
        update(OrderStatus.PARTIALLY_FILLED, 0.4, 100.0, last_qty=0.4)
    )
    await coordinator.broker_update(
        update(OrderStatus.PARTIALLY_FILLED, 0.7, 101.0, last_qty=0.3)
    )
    await coordinator.broker_update(
        update(OrderStatus.FILLED, 1.0, 102.0, last_qty=0.3)
    )
    await coordinator.broker_update(
        update(OrderStatus.FILLED, 1.0, 102.0, last_qty=0.3)
    )

    position = positions.get("A", "BTCUSDT")
    assert position.quantity == pytest.approx(1.0)
    assert position.average_entry == pytest.approx(100.9)
