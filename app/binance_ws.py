from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import websockets

from .event_bus import EventBus, TradingEvent


EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
ConnectionHandler = Callable[[], Awaitable[None]]


@dataclass
class BinanceWebSocketConfig:
    url: str = "wss://ws-api.binance.com:443/ws-api/v3"
    reconnect_seconds: float = 3.0
    ping_interval: float = 20.0
    recv_window: int = 5000


class BinanceWebSocketClient:
    """Resilient Binance Spot WebSocket API transport.

    User-data subscriptions use Binance's current signed WebSocket API
    subscription method. The connection lifecycle is exposed through
    async callbacks so execution safety can block trading during recovery.
    """

    def __init__(
        self,
        config: BinanceWebSocketConfig | None = None,
        event_bus: EventBus | None = None,
        on_disconnect: ConnectionHandler | None = None,
        on_recovered: ConnectionHandler | None = None,
    ):
        self.config = config or BinanceWebSocketConfig()
        self.event_bus = event_bus or EventBus()
        self.on_disconnect = on_disconnect
        self.on_recovered = on_recovered
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._request_id = 0

    async def start(
        self,
        handler: EventHandler | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self.run_forever(handler, api_key, api_secret)
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def run_forever(
        self,
        handler: EventHandler | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        if (api_key and not api_secret) or (api_secret and not api_key):
            raise ValueError("api_key and api_secret must be supplied together")

        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    self.config.url,
                    ping_interval=self.config.ping_interval,
                    ping_timeout=self.config.ping_interval,
                    close_timeout=5,
                ) as ws:
                    if api_key:
                        subscribed = await self.subscribe_user_stream(
                            ws, api_key, api_secret
                        )
                        if not subscribed:
                            raise RuntimeError("Binance user-data subscription was rejected")

                        # Broker truth must be reconciled before the account
                        # can become eligible for new execution.
                        if self.on_recovered is not None:
                            await self.on_recovered()

                    await self._consume(ws, handler)
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException, RuntimeError):
                if not self._stop.is_set():
                    if self.on_disconnect is not None:
                        await self.on_disconnect()
                    await asyncio.sleep(self.config.reconnect_seconds)

    @staticmethod
    def _signature(params: dict[str, Any], api_secret: str) -> str:
        payload = "&".join(
            f"{key}={str(params[key]).lower() if isinstance(params[key], bool) else params[key]}"
            for key in sorted(params)
        )
        return hmac.new(
            api_secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

    async def subscribe_user_stream(
        self,
        ws: Any,
        api_key: str,
        api_secret: str | None = None,
    ) -> bool:
        if not api_key.strip():
            raise ValueError("api_key is required")
        if not api_secret:
            raise ValueError("api_secret is required for signed user stream subscription")

        self._request_id += 1
        request_id = self._request_id
        params: dict[str, Any] = {
            "apiKey": api_key,
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.config.recv_window,
        }
        params["signature"] = self._signature(params, api_secret)

        await ws.send(
            json.dumps(
                {
                    "id": request_id,
                    "method": "userDataStream.subscribe.signature",
                    "params": params,
                }
            )
        )

        # Do not declare the account recovered until Binance acknowledges
        # the subscription request.
        while True:
            raw = await ws.recv()
            message = json.loads(raw)
            if message.get("id") != request_id:
                # Preserve unrelated messages so the caller can observe them
                # through the normal stream handler after subscription.
                await self.event_bus.publish(
                    TradingEvent.create(
                        "BROKER_WS_EVENT",
                        payload=message,
                        broker_event_type=self._event_type(message),
                    )
                )
                continue
            status = message.get("status")
            return status == 200 and not message.get("error")

    @staticmethod
    def _event_type(message: dict[str, Any]) -> str:
        event = message.get("event")
        if isinstance(event, dict):
            return str(event.get("e") or message.get("method") or "UNKNOWN")
        return str(message.get("event") or message.get("method") or "UNKNOWN")

    async def _consume(
        self,
        ws: Any,
        handler: EventHandler | None,
    ) -> None:
        async for raw in ws:
            message = json.loads(raw)
            if handler:
                await handler(message)

            await self.event_bus.publish(
                TradingEvent.create(
                    "BROKER_WS_EVENT",
                    payload=message,
                    broker_event_type=self._event_type(message),
                )
            )


class BinanceEventNormalizer:
    @staticmethod
    def normalize(message: dict[str, Any], account_id: str) -> TradingEvent:
        event = message.get("event")
        payload = event if isinstance(event, dict) else message
        event_type = payload.get("e") or payload.get("event") or message.get("method") or "UNKNOWN"
        mapping = {
            "executionReport": "ORDER_UPDATE",
            "outboundAccountPosition": "POSITION_UPDATE",
            "balanceUpdate": "BALANCE_UPDATE",
            "eventStreamTerminated": "STREAM_TERMINATED",
            "ACCOUNT_UPDATE": "ACCOUNT_UPDATE",
        }
        return TradingEvent.create(
            mapping.get(event_type, event_type),
            account_id,
            broker_event=payload,
        )
