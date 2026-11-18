import asyncio
import json

from app.binance_ws import BinanceWebSocketClient


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self._messages = [
            json.dumps({
                "id": 1,
                "status": 200,
                "result": {"subscriptionId": 7},
            })
        ]

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        return self._messages.pop(0)


def test_signed_subscription_requires_success_ack():
    async def run():
        ws = FakeWebSocket()
        client = BinanceWebSocketClient()

        ok = await client.subscribe_user_stream(
            ws,
            "api-key",
            "api-secret",
        )

        assert ok is True
        assert ws.sent[0]["method"] == "userDataStream.subscribe.signature"
        assert ws.sent[0]["params"]["apiKey"] == "api-key"
        assert ws.sent[0]["params"]["signature"]

    asyncio.run(run())
