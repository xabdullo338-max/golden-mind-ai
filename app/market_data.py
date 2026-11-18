from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class MarketTick:
    broker: str
    symbol: str
    price: float
    timestamp: datetime

    def __post_init__(self):
        if self.price <= 0:
            raise ValueError("price must be positive")
