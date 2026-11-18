import asyncio
from app.event_bus import EventBus
from app.execution_coordinator import ExecutionCoordinator
from app.journal import TradingJournal
from app.order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate

def test_broker_update_updates_lifecycle_journal_and_event(tmp_path):
    async def run():
        bus = EventBus()
        q = bus.subscribe()
        coordinator = ExecutionCoordinator(OrderLifecycle(), TradingJournal(str(tmp_path / "db.sqlite")), bus)
        update = OrderUpdate(
            broker="BINANCE", account_id="A", client_order_id="c1",
            status=OrderStatus.FILLED, symbol="BTCUSDT",
            executed_quantity=0.01, average_price=60000, broker_order_id="42",
        )
        applied = await coordinator.broker_update(update)
        assert applied.status == OrderStatus.FILLED
        assert coordinator.journal.get_order("c1")["status"] == "FILLED"
        event = await asyncio.wait_for(q.get(), 0.1)
        assert event.event_type == "ORDER_FILLED"
    asyncio.run(run())

def test_expired_is_not_open(tmp_path):
    journal = TradingJournal(str(tmp_path / "db.sqlite"))
    journal.upsert_order(__import__("app.journal", fromlist=["JournalOrder"]).JournalOrder(
        "c1","A","BINANCE","BTCUSDT","BUY",1,"EXPIRED"
    ))
    assert journal.list_open_orders() == []
