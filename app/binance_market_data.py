from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

import websockets

from .event_bus import EventBus, TradingEvent
from .market_data import MarketTick

TickHandler = Callable[[MarketTick], Awaitable[None]]

@dataclass(frozen=True)
class BinanceMarketStreamConfig:
    symbols: tuple[str, ...] = ("btcusdt", "ethusdt")
    url: str = "wss://stream.binance.com:9443/stream"
    reconnect_seconds: float = 2.0
    ping_interval: float = 20.0

class BinanceMarketDataStream:
    """Public Binance book-ticker stream with reconnect and normalization."""

    def __init__(self, config: BinanceMarketStreamConfig | None = None,
                 event_bus: EventBus | None = None):
        self.config = config or BinanceMarketStreamConfig()
        self.event_bus = event_bus or EventBus()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    def stream_url(self) -> str:
        streams = "/".join(f"{s.lower()}@bookTicker" for s in self.config.symbols)
        return f"{self.config.url}?streams={streams}"

    async def start(self, handler: TickHandler) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self.run_forever(handler))

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def run_forever(self, handler: TickHandler) -> None:
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    self.stream_url(),
                    ping_interval=self.config.ping_interval,
                    ping_timeout=self.config.ping_interval,
                    close_timeout=5,
                ) as ws:
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        message = json.loads(raw)
                        tick = self._normalize(message)
                        if tick is not None:
                            await handler(tick)
                            await self.event_bus.publish(
                                TradingEvent.create(
                                    "MARKET_TICK",
                                    payload={
                                        "broker": tick.broker,
                                        "symbol": tick.symbol,
                                        "price": tick.price,
                                        "bid": tick.bid,
                                        "ask": tick.ask,
                                        "timestamp": tick.timestamp.isoformat(),
                                    },
                                )
                            )
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException):
                if not self._stop.is_set():
                    await asyncio.sleep(self.config.reconnect_seconds)

    @staticmethod
    def _normalize(message: dict[str, Any]) -> MarketTick | None:
        data = message.get("data", message)
        symbol = data.get("s")
        bid = data.get("b")
        ask = data.get("a")
        if not symbol or bid is None or ask is None:
            return None
        bid_f, ask_f = float(bid), float(ask)
        return MarketTick(
            broker="BINANCE",
            symbol=symbol.upper(),
            price=(bid_f + ask_f) / 2,
            bid=bid_f,
            ask=ask_f,
            timestamp=datetime.now(UTC),
        )
