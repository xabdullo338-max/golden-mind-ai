from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
import websockets
from .event_bus import EventBus, TradingEvent

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]

@dataclass
class BinanceWebSocketConfig:
    url: str = "wss://stream.binance.com:9443/ws-api/v3"
    reconnect_seconds: float = 3.0
    ping_interval: float = 20.0

class BinanceWebSocketClient:
    """Resilient Binance Spot WebSocket API transport.

    The client can subscribe to user-data streams using a listen key supplied
    by the account/session layer. It never contains trading policy.
    """

    def __init__(self, config: BinanceWebSocketConfig | None = None,
                 event_bus: EventBus | None = None):
        self.config = config or BinanceWebSocketConfig()
        self.event_bus = event_bus or EventBus()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._request_id = 0

    async def start(self, handler: EventHandler | None = None,
                    listen_key: str | None = None) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self.run_forever(handler, listen_key))

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def run_forever(self, handler: EventHandler | None = None,
                          listen_key: str | None = None) -> None:
        url = self._stream_url(listen_key)
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    url, ping_interval=self.config.ping_interval,
                    ping_timeout=self.config.ping_interval, close_timeout=5,
                ) as ws:
                    await self._consume(ws, handler)
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException):
                if not self._stop.is_set():
                    await asyncio.sleep(self.config.reconnect_seconds)

    def _stream_url(self, listen_key: str | None) -> str:
        if not listen_key:
            return self.config.url
        return f"wss://stream.binance.com:9443/ws/{listen_key}"

    async def subscribe_user_stream(self, ws: Any, listen_key: str) -> None:
        # Kept as an explicit method so the session layer can evolve with
        # Binance's current user-stream protocol without mixing credentials
        # into the event consumer.
        if not listen_key.strip():
            raise ValueError("listen_key is required")
        self._request_id += 1
        await ws.send(json.dumps({
            "id": self._request_id,
            "method": "userDataStream.subscribe.signature",
            "params": {"apiKey": listen_key},
        }))

    async def _consume(self, ws: Any, handler: EventHandler | None) -> None:
        async for raw in ws:
            message = json.loads(raw)
            if handler:
                await handler(message)
            event_type = message.get("event") or message.get("method") or "UNKNOWN"
            await self.event_bus.publish(TradingEvent.create(
                "BROKER_WS_EVENT", payload=message, broker_event_type=event_type
            ))

class BinanceEventNormalizer:
    @staticmethod
    def normalize(message: dict[str, Any], account_id: str) -> TradingEvent:
        event_type = message.get("event") or message.get("method") or "UNKNOWN"
        mapping = {
            "executionReport": "ORDER_UPDATE",
            "outboundAccountPosition": "POSITION_UPDATE",
            "balanceUpdate": "BALANCE_UPDATE",
            "ACCOUNT_UPDATE": "ACCOUNT_UPDATE",
            "executionReport": "ORDER_UPDATE",
        }
        return TradingEvent.create(mapping.get(event_type, event_type),
                                    account_id, broker_event=message)
