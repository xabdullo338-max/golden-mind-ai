from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class StrategyDecision:
    signal: Signal
    confidence: float
    stop_price: float | None = None
    take_profit_price: float | None = None
    reason: str = ""


class TrendMomentumStrategy:
    """Deterministic, indicator-light 1m trend/momentum strategy.

    This module is intentionally dependency-free so the API/CI layer can import
    the strategy without requiring a broker connection. It does not execute
    orders; LiveStrategyRunner is responsible for execution and risk gates.
    """

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        momentum_period: int = 5,
        stop_atr_multiplier: float = 1.5,
        take_profit_r_multiple: float = 2.0,
    ) -> None:
        if fast_period < 2 or slow_period <= fast_period:
            raise ValueError("slow_period must be greater than fast_period >= 2")
        if momentum_period < 1:
            raise ValueError("momentum_period must be positive")
        if stop_atr_multiplier <= 0 or take_profit_r_multiple <= 0:
            raise ValueError("risk multipliers must be positive")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.momentum_period = momentum_period
        self.stop_atr_multiplier = stop_atr_multiplier
        self.take_profit_r_multiple = take_profit_r_multiple

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        if len(values) < period:
            raise ValueError("not enough values for EMA")
        alpha = 2.0 / (period + 1)
        value = mean(values[:period])
        for price in values[period:]:
            value = alpha * price + (1 - alpha) * value
        return value

    @staticmethod
    def _atr(candles: list[Candle], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 0.0
        true_ranges: list[float] = []
        for previous, current in zip(candles[-period - 1:-1], candles[-period:]):
            true_ranges.append(
                max(
                    current.high - current.low,
                    abs(current.high - previous.close),
                    abs(current.low - previous.close),
                )
            )
        return mean(true_ranges)

    def evaluate(self, candles: list[Candle]) -> StrategyDecision:
        if len(candles) < self.slow_period + self.momentum_period:
            return StrategyDecision(Signal.HOLD, 0.0, reason="not enough candles")

        closes = [float(c.close) for c in candles]
        fast = self._ema(closes, self.fast_period)
        slow = self._ema(closes, self.slow_period)
        current = closes[-1]
        previous = closes[-1 - self.momentum_period]
        momentum_pct = (current - previous) / previous * 100 if previous else 0.0
        atr = self._atr(candles)

        # Require a meaningful move, while keeping the threshold small enough
        # for 1-minute data. The runner still applies independent risk limits.
        threshold = max(0.02, min(0.20, (atr / current * 100) * 0.25 if current else 0.02))
        trend_gap_pct = abs(fast - slow) / current * 100 if current else 0.0
        confidence = min(0.99, max(0.0, 0.5 + trend_gap_pct * 5 + abs(momentum_pct) * 2))

        if fast > slow and momentum_pct >= threshold:
            stop = current - max(atr * self.stop_atr_multiplier, current * 0.001)
            risk = current - stop
            target = current + risk * self.take_profit_r_multiple
            return StrategyDecision(
                Signal.BUY,
                confidence,
                stop_price=stop,
                take_profit_price=target,
                reason="fast EMA above slow EMA with positive momentum",
            )

        if fast < slow and momentum_pct <= -threshold:
            stop = current + max(atr * self.stop_atr_multiplier, current * 0.001)
            risk = stop - current
            target = current - risk * self.take_profit_r_multiple
            return StrategyDecision(
                Signal.SELL,
                confidence,
                stop_price=stop,
                take_profit_price=target,
                reason="fast EMA below slow EMA with negative momentum",
            )

        return StrategyDecision(Signal.HOLD, confidence, reason="trend/momentum confirmation absent")
