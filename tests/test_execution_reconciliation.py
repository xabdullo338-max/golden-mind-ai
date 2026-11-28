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

    events = coordinator.event_bus.subscribe()

    await coordinator.broker_update(first)
    await coordinator.broker_update(duplicate)

    position = coordinator.positions.get("A", "BTCUSDT")
    assert position.quantity == pytest.approx(0.4)

    emitted = []
    while not events.empty():
        emitted.append(events.get_nowait())
    execution_events = [
        event for event in emitted
        if event.event_type == "ORDER_PARTIALLY_FILLED"
    ]
    assert len(execution_events) == 1


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
    # The lifecycle layer rejects delayed lower cumulative fills before they
    # reach the durable execution ledger. They must be ignored, not re-applied.
    await coordinator.broker_update(make_update(OrderStatus.PARTIALLY_FILLED, 0.4, price=100.0))

    position = coordinator.positions.get("A", "BTCUSDT")
    assert position.quantity == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_concurrent_duplicate_filled_updates_apply_once():
    coordinator = ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    await coordinator.submitted("A", "BINANCE", "o-race", "BTCUSDT", "BUY", 1.0)

    update = make_update(
        OrderStatus.FILLED,
        1.0,
        client="o-race",
        price=100.0,
        last_qty=1.0,
        last_price=100.0,
    )

    await __import__("asyncio").gather(
        coordinator.broker_update(update),
        coordinator.broker_update(update),
    )

    position = coordinator.positions.get("A", "BTCUSDT")
    assert position is not None
    assert position.quantity == pytest.approx(1.0)

    replay = await coordinator.broker_update(update)
    assert replay.executed_quantity == pytest.approx(1.0)
    assert coordinator.positions.get("A", "BTCUSDT").quantity == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_final_fill_then_delayed_partial_is_ignored():
    coordinator = ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    await coordinator.submitted("A", "BINANCE", "o-order", "BTCUSDT", "BUY", 1.0)

    final = make_update(
        OrderStatus.FILLED,
        1.0,
        client="o-order",
        price=101.0,
        last_qty=0.4,
        last_price=101.5,
    )
    delayed_partial = make_update(
        OrderStatus.PARTIALLY_FILLED,
        0.6,
        client="o-order",
        price=100.5,
        last_qty=0.2,
        last_price=100.0,
    )

    await coordinator.broker_update(final)
    await coordinator.broker_update(delayed_partial)

    position = coordinator.positions.get("A", "BTCUSDT")
    assert position is not None
    assert position.quantity == pytest.approx(1.0)
    assert coordinator.lifecycle.get("o-order", "A", "BINANCE").status is OrderStatus.FILLED


@pytest.mark.asyncio
async def test_partial_then_final_and_replayed_partial_apply_exact_delta():
    coordinator = ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    await coordinator.submitted("A", "BINANCE", "o-delta", "BTCUSDT", "BUY", 1.0)

    partial = make_update(
        OrderStatus.PARTIALLY_FILLED,
        0.4,
        client="o-delta",
        price=100.0,
        last_qty=0.4,
        last_price=100.0,
    )
    final = make_update(
        OrderStatus.FILLED,
        1.0,
        client="o-delta",
        price=101.0,
        last_qty=0.6,
        last_price=101.6666666667,
    )

    await coordinator.broker_update(partial)
    await coordinator.broker_update(final)
    await coordinator.broker_update(partial)
    await coordinator.broker_update(final)

    position = coordinator.positions.get("A", "BTCUSDT")
    assert position is not None
    assert position.quantity == pytest.approx(1.0)
    assert coordinator.execution_ledger.delta(
        "o-delta", 1.0, account_id="A", broker="BINANCE"
    ) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_ibkr_partial_then_filled_replay_applies_exact_delta():
    from app.brokers.ibkr import IBKRAdapter

    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")
    coordinator = ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    await coordinator.submitted(
        "IBKR-01", "IBKR", "GMAI-IBKR-1", "AAPL", "BUY", 1.0
    )

    partial_raw = {
        "orderId": 9003,
        "ticker": "AAPL",
        "side": "BUY",
        "status": "PartiallyFilled",
        "totalSize": "1",
        "filledQuantity": "0.4",
        "avgPrice": "210.00",
        "order_ref": "GMAI-IBKR-1",
    }
    final_raw = {
        **partial_raw,
        "status": "Filled",
        "filledQuantity": "1.0",
        "avgPrice": "211.00",
    }

    partial = adapter._normalize_order(partial_raw)
    final = adapter._normalize_order(final_raw)
    assert partial is not None
    assert final is not None

    await coordinator.broker_update(OrderUpdate(
        broker="IBKR",
        account_id="IBKR-01",
        client_order_id=partial["clientOrderId"],
        status=OrderStatus(partial["status"]),
        symbol=partial["symbol"],
        executed_quantity=partial["executedQty"],
        average_price=partial["avgPrice"],
        broker_order_id=partial["orderId"],
        side=partial["side"],
        original_quantity=partial["origQty"],
    ))
    await coordinator.broker_update(OrderUpdate(
        broker="IBKR",
        account_id="IBKR-01",
        client_order_id=final["clientOrderId"],
        status=OrderStatus(final["status"]),
        symbol=final["symbol"],
        executed_quantity=final["executedQty"],
        average_price=final["avgPrice"],
        broker_order_id=final["orderId"],
        side=final["side"],
        original_quantity=final["origQty"],
    ))

    # Replays must not create a second position delta.
    await coordinator.broker_update(OrderUpdate(
        broker="IBKR",
        account_id="IBKR-01",
        client_order_id=partial["clientOrderId"],
        status=OrderStatus(partial["status"]),
        symbol=partial["symbol"],
        executed_quantity=partial["executedQty"],
        average_price=partial["avgPrice"],
        broker_order_id=partial["orderId"],
        side=partial["side"],
        original_quantity=partial["origQty"],
    ))
    await coordinator.broker_update(OrderUpdate(
        broker="IBKR",
        account_id="IBKR-01",
        client_order_id=final["clientOrderId"],
        status=OrderStatus(final["status"]),
        symbol=final["symbol"],
        executed_quantity=final["executedQty"],
        average_price=final["avgPrice"],
        broker_order_id=final["orderId"],
        side=final["side"],
        original_quantity=final["origQty"],
    ))

    position = coordinator.positions.get("IBKR-01", "AAPL")
    assert position is not None
    assert position.quantity == pytest.approx(1.0)
    assert coordinator.execution_ledger.delta(
        "GMAI-IBKR-1", 1.0, account_id="IBKR-01", broker="IBKR"
    ) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_live_execution_is_deferred_until_recovery_finishes():
    coordinator = ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(":memory:"),
    )
    await coordinator.submitted(
        "IBKR-01", "IBKR", "GMAI-GATE-1", "AAPL", "BUY", 1.0
    )

    coordinator.begin_recovery()
    live_partial = OrderUpdate(
        broker="IBKR",
        account_id="IBKR-01",
        client_order_id="GMAI-GATE-1",
        status=OrderStatus.PARTIALLY_FILLED,
        symbol="AAPL",
        executed_quantity=0.4,
        average_price=210.0,
        broker_order_id="9100",
        side="BUY",
        original_quantity=1.0,
    )

    # Live websocket state is deferred while recovery is authoritative.
    deferred = await coordinator.broker_update(live_partial)
    assert deferred.status is OrderStatus.PARTIALLY_FILLED
    assert coordinator.positions.get("IBKR-01", "AAPL") is None

    # Recovery discovers the broker's final FILLED state and applies it
    # while the gate is active. The deferred stale partial must not add 0.4.
    recovered = OrderUpdate(
        broker="IBKR",
        account_id="IBKR-01",
        client_order_id="GMAI-GATE-1",
        status=OrderStatus.FILLED,
        symbol="AAPL",
        executed_quantity=1.0,
        average_price=211.0,
        broker_order_id="9100",
        side="BUY",
        original_quantity=1.0,
    )
    await coordinator.broker_update(recovered, allow_during_recovery=True)

    await coordinator.end_recovery()

    position = coordinator.positions.get("IBKR-01", "AAPL")
    assert position is not None
    assert position.quantity == pytest.approx(1.0)
    assert coordinator.lifecycle.get(
        "GMAI-GATE-1", "IBKR-01", "IBKR"
    ).status is OrderStatus.FILLED
