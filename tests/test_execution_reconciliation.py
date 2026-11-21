import pytest

from app.binance_events import execution_report_to_update
from app.event_bus import EventBus
from app.execution_coordinator import ExecutionCoordinator
from app.execution_ledger import ExecutionLedger
from app.journal import TradingJournal
from app.order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate
from app.position_engine import PositionEngine


def make_update(status, cumulative, side="BUY", client="order-1", price=100.0, last_qty=None, last_price=None):
    return OrderUpdate(
        broker="BINANCE",
        account_id="A",
        client_order_id=client,
        status=status,
        symbol="BTCUSDT",
        executed_quantity=cumulative,
        average_price=price if cumulative else None,
        broker_order_id="42",
        side=side,
        last_fill_quantity=last_qty,
        last_fill_price=last_price,
    )


def test_duplicate_execution_report_has_zero_position_delta():
    ledger = ExecutionLedger()
    assert ledger.delta("o-1", 0.4, "A", "BINANCE") == 0.4
    assert ledger.delta("o-1", 0.4, "A", "BINANCE") == 0.0
    assert ledger.delta("o-1", 1.0, "A", "BINANCE") == 0.6


def test_cumulative_execution_only_applies_new_fill():
    ledger = ExecutionLedger()
    assert ledger.delta("o-1", 0.4, "A", "BINANCE") == 0.4
    assert ledger.delta("o-1", 1.0, "A", "BINANCE") == pytest.approx(0.6)


def test_execution_ledger_survives_process_restart(tmp_path):
    path = str(tmp_path / "execution.db")
    first = ExecutionLedger(path)
    assert first.delta("o-1", 0.4, "A", "BINANCE") == 0.4

    restarted = ExecutionLedger(path)
    assert restarted.delta("o-1", 0.4, "A", "BINANCE") == 0.0
    assert restarted.delta("o-1", 1.0, "A", "BINANCE") == pytest.approx(0.6)


def test_cumulative_execution_cannot_move_backwards():
    ledger = ExecutionLedger()
    ledger.delta("o-1", 1.0, "A", "BINANCE")
    with pytest.raises(ValueError, match="moved backwards"):
        ledger.delta("o-1", 0.9, "A", "BINANCE")


def test_binance_execution_report_normalizes_last_fill_fields():
    update = execution_report_to_update(
        {
            "e": "executionReport",
            "X": "PARTIALLY_FILLED",
            "s": "BTCUSDT",
            "c": "o-1",
            "S": "BUY",
            "z": "1.00000000",
            "Z": "101.00000000",
            "l": "0.60000000",
            "L": "101.66666667",
            "i": 42,
        },
        "A",
    )
    assert update is not None
    assert update.executed_quantity == pytest.approx(1.0)
    assert update.average_price == pytest.approx(101.0)
    assert update.last_fill_quantity == pytest.approx(0.6)
    assert update.last_fill_price == pytest.approx(101.66666667)


@pytest.mark.asyncio
async def test_coordinator_duplicate_fill_does_not_change_position_twice():
    coordinator = ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    await coordinator.submitted("A", "BINANCE", "o-1", "BTCUSDT", "BUY", 1.0)

    first = make_update(OrderStatus.PARTIALLY_FILLED, 0.4, price=100.0)
    duplicate = make_update(OrderStatus.PARTIALLY_FILLED, 0.4, price=100.0)

    await coordinator.broker_update(first)
    await coordinator.broker_update(duplicate)

    position = coordinator.positions.get("A", "BTCUSDT")
    assert position.quantity == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_coordinator_applies_only_incremental_quantity():
    coordinator = ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    await coordinator.submitted("A", "BINANCE", "o-1", "BTCUSDT", "BUY", 1.0)

    await coordinator.broker_update(make_update(OrderStatus.PARTIALLY_FILLED, 0.4, price=100.0, last_qty=0.4, last_price=100.0))
    await coordinator.broker_update(make_update(OrderStatus.FILLED, 1.0, price=101.0, last_qty=0.6, last_price=101.6666666667))

    position = coordinator.positions.get("A", "BTCUSDT")
    assert position.quantity == pytest.approx(1.0)
    assert position.average_entry == pytest.approx(101.0)


@pytest.mark.asyncio
async def test_out_of_order_lower_cumulative_fill_is_rejected():
    coordinator = ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    await coordinator.submitted("A", "BINANCE", "o-1", "BTCUSDT", "BUY", 1.0)

    await coordinator.broker_update(make_update(OrderStatus.PARTIALLY_FILLED, 0.7, price=100.0))
    with pytest.raises(ValueError, match="moved backwards"):
        await coordinator.broker_update(make_update(OrderStatus.PARTIALLY_FILLED, 0.4, price=100.0))
