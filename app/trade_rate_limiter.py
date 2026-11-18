from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic

@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str

class TradeRateLimiter:
    """Controls trade frequency without forcing the strategy to trade."""

    def __init__(self, max_trades_per_hour: int = 100, cooldown_seconds: float = 0.0):
        if max_trades_per_hour <= 0:
            raise ValueError("max_trades_per_hour must be positive")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")
        self.max_trades_per_hour = max_trades_per_hour
        self.cooldown_seconds = cooldown_seconds
        self._timestamps: deque[float] = deque()

    def check(self) -> RateLimitDecision:
        now = monotonic()
        self._prune(now)
        if self._timestamps and now - self._timestamps[-1] < self.cooldown_seconds:
            return RateLimitDecision(False, "cooldown active")
        if len(self._timestamps) >= self.max_trades_per_hour:
            return RateLimitDecision(False, "hourly trade limit reached")
        return RateLimitDecision(True, "allowed")

    def record(self) -> None:
        decision = self.check()
        if not decision.allowed:
            raise RuntimeError(decision.reason)
        self._timestamps.append(monotonic())

    def count_last_hour(self) -> int:
        now = monotonic()
        self._prune(now)
        return len(self._timestamps)

    def _prune(self, now: float) -> None:
        cutoff = now - 3600.0
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()
