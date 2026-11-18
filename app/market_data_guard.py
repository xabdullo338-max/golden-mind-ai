from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .market_data import MarketTick


@dataclass(frozen=True)
class MarketDataFreshnessGuard:
    """Rejects ticks that are too old for execution decisions."""

    max_age_seconds: float = 2.0

    def is_fresh(self, tick: MarketTick, *, now: datetime | None = None) -> bool:
        if self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        current = now or datetime.now(UTC)
        timestamp = tick.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        age = (current - timestamp).total_seconds()
        return age >= 0 and age <= self.max_age_seconds

    def assert_fresh(self, tick: MarketTick, *, now: datetime | None = None) -> None:
        if not self.is_fresh(tick, now=now):
            raise RuntimeError(
                f"stale market data: {tick.symbol} is older than "
                f"{self.max_age_seconds:.3f}s"
            )
