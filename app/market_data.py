from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class MarketTick:
    broker: str
    symbol: str
    price: float
    timestamp: datetime
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.bid is not None and self.bid <= 0:
            raise ValueError("bid must be positive")
        if self.ask is not None and self.ask <= 0:
            raise ValueError("ask must be positive")
        if self.bid is not None and self.ask is not None and self.ask < self.bid:
            raise ValueError("ask cannot be below bid")

    @property
    def spread_pct(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.ask - self.bid) / ((self.ask + self.bid) / 2) * 100

    @property
    def spread_bps(self) -> float | None:
        value = self.spread_pct
        return None if value is None else value * 100
