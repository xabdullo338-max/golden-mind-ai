import asyncio
from app.event_bus import EventBus
from app.binance_ws import BinanceEventNormalizer

def test_normalizes_order_update():
    event = BinanceEventNormalizer.normalize(
        {"event": "executionReport", "s": "BTCUSDT", "X": "FILLED"},
        "BINANCE-01",
    )
    assert event.event_type == "ORDER_UPDATE"
    assert event.account_id == "BINANCE-01"

def test_normalizes_balance_update():
    event = BinanceEventNormalizer.normalize(
        {"event": "balanceUpdate", "a": "USDT"},
        "BINANCE-01",
    )
    assert event.event_type == "BALANCE_UPDATE"

def test_event_bus_is_async():
    async def run():
        bus = EventBus()
        q = bus.subscribe()
        await bus.publish(BinanceEventNormalizer.normalize({"event": "executionReport"}, "A"))
        received = await asyncio.wait_for(q.get(), 0.1)
        assert received.event_type == "BROKER_WS_EVENT"
    asyncio.run(run())
