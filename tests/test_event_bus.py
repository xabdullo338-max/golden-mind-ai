import asyncio
from app.event_bus import EventBus, TradingEvent

def test_publish_reaches_subscriber():
    async def scenario():
        bus = EventBus()
        q = bus.subscribe()
        event = TradingEvent.create("ORDER_FILLED", "BINANCE-01", symbol="BTCUSDT", qty=0.01)
        await bus.publish(event)
        received = await asyncio.wait_for(q.get(), timeout=0.1)
        assert received.event_type == "ORDER_FILLED"
        assert received.account_id == "BINANCE-01"
        assert received.payload["symbol"] == "BTCUSDT"
    asyncio.run(scenario())

def test_unsubscribe():
    bus = EventBus()
    q = bus.subscribe()
    bus.unsubscribe(q)
    assert bus.subscriber_count == 0
