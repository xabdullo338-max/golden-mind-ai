import asyncio

from app.binance_events import execution_report_to_update
from app.binance_execution_bridge import BinanceExecutionBridge
from app.event_bus import EventBus
from app.execution_coordinator import ExecutionCoordinator
from app.journal import TradingJournal
from app.order_lifecycle import OrderLifecycle, OrderStatus
from app.position_engine import PositionEngine


def report(status: str, cumulative_qty: str, quote_qty: str, *,
           account: str = "A", client_id: str = "cid-1") -> dict:
    return {
        "subscriptionId": 0,
        "event": {
            "e": "executionReport",
            "s": "BTCUSDT",
            "c": client_id,
            "S": "BUY",
            "X": status,
            "z": cumulative_qty,
            "Z": quote_qty,
            "i": 42,
        },
    }


def test_execution_report_maps_side_and_average_price():
    update = execution_report_to_update(report("PARTIALLY_FILLED", "0.004", "240.0")["event"], "A")
    assert update is not None
    assert update.side == "BUY"
    assert update.executed_quantity == 0.004
    assert update.average_price == 60000.0


def test_bridge_applies_partial_fill_deltas_without_double_count(tmp_path):
    async def run():
        bus = EventBus()
        coordinator = ExecutionCoordinator(
            OrderLifecycle(),
            TradingJournal(str(tmp_path / "db.sqlite")),
            bus,
            positions=PositionEngine(),
        )
        await coordinator.submitted("A", "BINANCE", "cid-1", "BTCUSDT", "BUY", 0.01)
        bridge = BinanceExecutionBridge("A", coordinator)

        await bridge.handle(report("NEW", "0", "0.0"))
        await bridge.handle(report("PARTIALLY_FILLED", "0.004", "240.0"))
        await bridge.handle(report("PARTIALLY_FILLED", "0.006", "360.0"))
        await bridge.handle(report("FILLED", "0.010", "600.0"))
        await bridge.handle(report("FILLED", "0.010", "600.0"))

        position = coordinator.positions.get("A", "BTCUSDT")
        assert position.quantity == 0.01
        assert position.average_entry == 60000.0
        assert coordinator.journal.get_order("cid-1")["status"] == "FILLED"

    asyncio.run(run())


def test_lifecycle_and_ledger_are_account_scoped():
    from app.order_lifecycle import OrderLifecycle, OrderUpdate
    from app.execution_ledger import ExecutionLedger

    lifecycle = OrderLifecycle()
    ledger = ExecutionLedger()
    u1 = OrderUpdate("BINANCE", "A", "same", OrderStatus.FILLED, "BTCUSDT", 1.0)
    u2 = OrderUpdate("BINANCE", "B", "same", OrderStatus.FILLED, "BTCUSDT", 2.0)

    lifecycle.apply(u1)
    lifecycle.apply(u2)
    assert lifecycle.get("same", account_id="A", broker="BINANCE").executed_quantity == 1.0
    assert lifecycle.get("same", account_id="B", broker="BINANCE").executed_quantity == 2.0
    assert ledger.delta("same", 1.0, account_id="A", broker="BINANCE") == 1.0
    assert ledger.delta("same", 2.0, account_id="B", broker="BINANCE") == 2.0
