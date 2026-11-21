from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .market_data import MarketTick


@dataclass
class MarketDataStore:
    """Small in-process market-data cache with explicit freshness checks."""

    _ticks: dict[tuple[str, str], MarketTick]

    def __init__(self) -> None:
        self._ticks = {}

    def update(self, tick: MarketTick) -> None:
        self._ticks[(tick.broker.upper(), tick.symbol.upper())] = tick

    def get(self, broker: str, symbol: str) -> MarketTick | None:
        return self._ticks.get((broker.upper(), symbol.upper()))

    def age_seconds(
        self,
        broker: str,
        symbol: str,
        *,
        now: datetime | None = None,
    ) -> float | None:
        tick = self.get(broker, symbol)
        if tick is None:
            return None
        current = now or datetime.now(timezone.utc)
        timestamp = tick.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0.0, (current - timestamp).total_seconds())

    def price_map(self, broker: str) -> dict[str, float]:
        result: dict[str, float] = {}
        prefix = broker.upper()
        for (item_broker, symbol), tick in self._ticks.items():
            if item_broker == prefix:
                result[symbol] = tick.price
                if symbol.endswith("USDT"):
                    result[symbol.removesuffix("USDT")] = tick.price
        return result

    def require_fresh(
        self,
        broker: str,
        symbol: str,
        max_age_seconds: float,
        *,
        now: datetime | None = None,
    ) -> MarketTick:
        tick = self.get(broker, symbol)
        if tick is None:
            raise RuntimeError(f"market data unavailable for {symbol}")
        age = self.age_seconds(broker, symbol, now=now)
        if age is None or age > max_age_seconds:
            raise RuntimeError(f"market data is stale for {symbol}")
        return tick
