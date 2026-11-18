from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class ScalpingFilterConfig:
    min_move_pct: float = 0.03
    max_spread_pct: float = 0.08
    min_price: float = 0.0

@dataclass(frozen=True)
class ScalpingFilter:
    config: ScalpingFilterConfig = ScalpingFilterConfig()

    def accept(self, price: float, reference_price: float, bid: float | None = None,
               ask: float | None = None) -> bool:
        if price <= self.config.min_price or reference_price <= 0:
            return False
        move_pct = abs(price - reference_price) / reference_price * 100
        if move_pct < self.config.min_move_pct:
            return False
        if bid is not None and ask is not None:
            if bid <= 0 or ask <= 0 or ask < bid:
                return False
            spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
            if spread_pct > self.config.max_spread_pct:
                return False
        return True
