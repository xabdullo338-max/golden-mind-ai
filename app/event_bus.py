from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

@dataclass(frozen=True)
class TradingEvent:
    event_type: str
    account_id: str | None
    payload: dict[str, Any]
    timestamp: str

    @classmethod
    def create(cls, event_type: str, account_id: str | None = None, **payload: Any) -> "TradingEvent":
        return cls(event_type, account_id, payload, datetime.now(UTC).isoformat())

class EventBus:
    """In-process async pub/sub bus used by API, execution and broker adapters."""

    def __init__(self, max_queue_size: int = 256):
        self._subscribers: set[asyncio.Queue[TradingEvent]] = set()
        self.max_queue_size = max_queue_size

    def subscribe(self) -> asyncio.Queue[TradingEvent]:
        queue: asyncio.Queue[TradingEvent] = asyncio.Queue(self.max_queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[TradingEvent]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: TradingEvent) -> None:
        stale: list[asyncio.Queue[TradingEvent]] = []
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self.unsubscribe(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @staticmethod
    def serialize(event: TradingEvent) -> dict[str, Any]:
        return asdict(event)
