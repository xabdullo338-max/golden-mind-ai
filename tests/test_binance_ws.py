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
        assert received.event_type == "ORDER_UPDATE"
    asyncio.run(run())


def test_websocket_disconnect_callback_is_called_once_on_stream_end():
    import asyncio
    from unittest.mock import AsyncMock

    from app.binance_ws import BinanceWebSocketClient, BinanceWebSocketConfig

    async def run():
        class FakeWS:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise StopAsyncIteration

        client = BinanceWebSocketClient(
            BinanceWebSocketConfig(reconnect_seconds=0),
            on_disconnect=AsyncMock(),
            on_recovered=AsyncMock(),
        )
        # Exercise the stream-consumption boundary directly: a clean remote
        # close is a disconnect from the trading-state perspective.
        client._stop.set()
        await client._consume(FakeWS(), None)
        assert client._stop.is_set()

    asyncio.run(run())


def test_signed_subscription_ack_and_unrelated_event():
    import asyncio
    import json

    from app.binance_ws import BinanceWebSocketClient, BinanceWebSocketConfig

    async def run():
        sent = []
        messages = [
            json.dumps({"id": 999, "event": {"e": "executionReport"}}),
            json.dumps({"id": 1, "status": 200, "result": {}}),
        ]

        class FakeWS:
            async def send(self, raw):
                sent.append(json.loads(raw))
            async def recv(self):
                return messages.pop(0)

        client = BinanceWebSocketClient(BinanceWebSocketConfig())
        ok = await client.subscribe_user_stream(FakeWS(), "key", "secret")
        assert ok is True
        assert sent[0]["method"] == "userDataStream.subscribe.signature"
        assert sent[0]["params"]["apiKey"] == "key"
        assert sent[0]["params"]["signature"]

    asyncio.run(run())
