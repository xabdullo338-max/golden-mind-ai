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



@dataclass(frozen=True)
class IndicatorSnapshot:
    ema_fast: float
    ema_slow: float
    rsi: float
    atr: float
    atr_pct: float
    adx: float
    bb_mid: float
    bb_upper: float
    bb_lower: float
    volume_ratio: float
    momentum_pct: float
    trend_strength: float


class MarketRegime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class AdaptiveDecision(StrategyDecision):
    regime: MarketRegime = MarketRegime.UNCERTAIN
    indicators: IndicatorSnapshot | None = None
    model_score: float = 0.0
    ai_probability: float | None = None


class OnlineDirectionModel:
    """Lightweight online logistic model using only past candle information."""

    def __init__(self, learning_rate: float = 0.08, epochs: int = 80) -> None:
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.weights: list[float] = []
        self.bias = 0.0
        self.means: list[float] = []
        self.scales: list[float] = []

    @staticmethod
    def _features(candles: list[Candle], i: int) -> list[float]:
        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]
        price = closes[i]
        ret1 = (price - closes[i - 1]) / closes[i - 1] if closes[i - 1] else 0.0
        ret5 = (price - closes[i - 5]) / closes[i - 5] if closes[i - 5] else 0.0
        ema9 = TrendMomentumStrategy._ema(closes[:i + 1], 9)
        ema21 = TrendMomentumStrategy._ema(closes[:i + 1], 21)
        atr = TrendMomentumStrategy._atr(candles[:i + 1], 14)
        rsi = AdaptiveEnsembleStrategy._rsi(closes[:i + 1], 14)
        start = max(0, i - 19)
        volume_ratio = volumes[i] / max(mean(volumes[start:i + 1]), 1e-12)
        return [
            ret1,
            ret5,
            (ema9 - ema21) / max(price, 1e-12),
            atr / max(price, 1e-12),
            (rsi - 50.0) / 50.0,
            volume_ratio - 1.0,
        ]

    @staticmethod
    def _sigmoid(x: float) -> float:
        if x >= 0:
            z = 2.718281828459045 ** (-x)
            return 1.0 / (1.0 + z)
        z = 2.718281828459045 ** x
        return z / (1.0 + z)

    def fit(self, candles: list[Candle]) -> None:
        if len(candles) < 45:
            self.weights = []
            return
        x_raw: list[list[float]] = []
        y: list[float] = []
        for i in range(22, len(candles) - 1):
            x_raw.append(self._features(candles, i))
            y.append(1.0 if candles[i + 1].close > candles[i].close else 0.0)
        if not x_raw:
            self.weights = []
            return

        n = len(x_raw[0])
        self.means = [mean(row[j] for row in x_raw) for j in range(n)]
        self.scales = [
            max(mean([(row[j] - self.means[j]) ** 2 for row in x_raw]) ** 0.5, 1e-6)
            for j in range(n)
        ]
        x = [[(row[j] - self.means[j]) / self.scales[j] for j in range(n)] for row in x_raw]
        self.weights = [0.0] * n
        self.bias = 0.0

        for _ in range(self.epochs):
            grad_w = [0.0] * n
            grad_b = 0.0
            for row, target in zip(x, y):
                probability = self._sigmoid(self.bias + sum(w * v for w, v in zip(self.weights, row)))
                error = probability - target
                for j, value in enumerate(row):
                    grad_w[j] += error * value
                grad_b += error
            scale = 1.0 / len(x)
            self.weights = [
                w - self.learning_rate * grad * scale
                for w, grad in zip(self.weights, grad_w)
            ]
            self.bias -= self.learning_rate * grad_b * scale

    def predict_up_probability(self, candles: list[Candle]) -> float | None:
        if not self.weights or len(candles) < 23:
            return None
        row = self._features(candles, len(candles) - 1)
        normalized = [
            (row[j] - self.means[j]) / self.scales[j]
            for j in range(len(row))
        ]
        return self._sigmoid(
            self.bias + sum(w * v for w, v in zip(self.weights, normalized))
        )


class AdaptiveEnsembleStrategy:
    """Regime-aware ensemble combining technical indicators with a small ML layer.

    The ML model is trained only on earlier candles in the supplied window.
    The strategy remains conservative: uncertain/high-volatility regimes default
    to HOLD and all orders still pass the independent risk engine.
    """

    def __init__(self, min_confidence: float = 0.62) -> None:
        if not 0.5 <= min_confidence < 1.0:
            raise ValueError("min_confidence must be in [0.5, 1.0)")
        self.min_confidence = min_confidence
        self.ai_model = OnlineDirectionModel()

    @staticmethod
    def _sma(values: list[float], period: int) -> float:
        if len(values) < period:
            raise ValueError("not enough values for SMA")
        return mean(values[-period:])

    @staticmethod
    def _rsi(values: list[float], period: int = 14) -> float:
        if len(values) <= period:
            raise ValueError("not enough values for RSI")
        gains = []
        losses = []
        for a, b in zip(values[-period - 1:-1], values[-period:]):
            delta = b - a
            gains.append(max(delta, 0.0))
            losses.append(max(-delta, 0.0))
        avg_gain = mean(gains)
        avg_loss = mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    @staticmethod
    def _std(values: list[float]) -> float:
        m = mean(values)
        return mean([(v - m) ** 2 for v in values]) ** 0.5

    @staticmethod
    def _adx(candles: list[Candle], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 0.0
        plus_dm, minus_dm, trs = [], [], []
        for prev, cur in zip(candles[-period - 1:-1], candles[-period:]):
            up = cur.high - prev.high
            down = prev.low - cur.low
            plus_dm.append(up if up > down and up > 0 else 0.0)
            minus_dm.append(down if down > up and down > 0 else 0.0)
            trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
        atr = mean(trs)
        if atr <= 0:
            return 0.0
        plus_di = 100.0 * mean(plus_dm) / atr
        minus_di = 100.0 * mean(minus_dm) / atr
        denom = plus_di + minus_di
        return 100.0 * abs(plus_di - minus_di) / denom if denom else 0.0

    def indicators(self, candles: list[Candle]) -> IndicatorSnapshot:
        closes = [float(c.close) for c in candles]
        volumes = [float(c.volume) for c in candles]
        current = closes[-1]
        fast = TrendMomentumStrategy._ema(closes, 9)
        slow = TrendMomentumStrategy._ema(closes, 21)
        atr = TrendMomentumStrategy._atr(candles, 14)
        rsi = self._rsi(closes, 14)
        mid = self._sma(closes, 20)
        std = self._std(closes[-20:])
        volume_ratio = volumes[-1] / max(mean(volumes[-20:]), 1e-12)
        momentum_pct = (current - closes[-6]) / closes[-6] * 100 if closes[-6] else 0.0
        return IndicatorSnapshot(
            ema_fast=fast,
            ema_slow=slow,
            rsi=rsi,
            atr=atr,
            atr_pct=atr / max(current, 1e-12) * 100,
            adx=self._adx(candles),
            bb_mid=mid,
            bb_upper=mid + 2 * std,
            bb_lower=mid - 2 * std,
            volume_ratio=volume_ratio,
            momentum_pct=momentum_pct,
            trend_strength=min(1.0, abs(fast - slow) / max(current, 1e-12) * 100 / 0.5),
        )

    @staticmethod
    def _regime(i: IndicatorSnapshot) -> MarketRegime:
        if i.atr_pct >= 1.2:
            return MarketRegime.HIGH_VOLATILITY
        if i.adx >= 25 and i.ema_fast > i.ema_slow and i.momentum_pct > 0:
            return MarketRegime.TREND_UP
        if i.adx >= 25 and i.ema_fast < i.ema_slow and i.momentum_pct < 0:
            return MarketRegime.TREND_DOWN
        if i.adx < 20:
            return MarketRegime.RANGE
        return MarketRegime.UNCERTAIN

    def evaluate(self, candles: list[Candle]) -> AdaptiveDecision:
        if len(candles) < 45:
            return AdaptiveDecision(Signal.HOLD, 0.0, reason="not enough candles")

        indicators = self.indicators(candles)
        regime = self._regime(indicators)

        # Train only on the past portion; the current candle is excluded from
        # training labels to reduce look-ahead leakage.
        self.ai_model.fit(candles[:-1])
        ai_probability = self.ai_model.predict_up_probability(candles)

        trend_vote = 1.0 if indicators.ema_fast > indicators.ema_slow else -1.0
        momentum_vote = (
            1.0 if indicators.momentum_pct > 0.05
            else -1.0 if indicators.momentum_pct < -0.05
            else 0.0
        )
        rsi_vote = (
            1.0 if 50 < indicators.rsi < 72
            else -1.0 if 28 < indicators.rsi < 50
            else 0.0
        )
        volume_vote = 1.0 if indicators.volume_ratio >= 1.15 else 0.0

        score = (
            0.35 * trend_vote
            + 0.25 * momentum_vote
            + 0.15 * rsi_vote
            + 0.10 * volume_vote
        )
        if ai_probability is not None:
            score += 0.15 * (2.0 * ai_probability - 1.0)

        if regime == MarketRegime.TREND_UP:
            score += 0.10
        elif regime == MarketRegime.TREND_DOWN:
            score -= 0.10
        elif regime in {MarketRegime.HIGH_VOLATILITY, MarketRegime.UNCERTAIN}:
            score *= 0.45

        confidence = min(
            0.99,
            0.50 + abs(score) * 0.45 + indicators.trend_strength * 0.10,
        )

        if confidence < self.min_confidence or regime in {
            MarketRegime.HIGH_VOLATILITY,
            MarketRegime.UNCERTAIN,
        }:
            return AdaptiveDecision(
                Signal.HOLD,
                confidence,
                regime=regime,
                indicators=indicators,
                model_score=score,
                ai_probability=ai_probability,
                reason=f"regime gate: {regime.value}",
            )

        current = candles[-1].close
        risk_distance = max(indicators.atr * 1.8, current * 0.0015)
        if score > 0.25:
            stop = current - risk_distance
            return AdaptiveDecision(
                Signal.BUY,
                confidence,
                stop_price=stop,
                take_profit_price=current + risk_distance * 2.2,
                regime=regime,
                indicators=indicators,
                model_score=score,
                ai_probability=ai_probability,
                reason=f"ensemble BUY: trend+momentum+RSI+volume+ML; regime={regime.value}",
            )
        if score < -0.25:
            stop = current + risk_distance
            return AdaptiveDecision(
                Signal.SELL,
                confidence,
                stop_price=stop,
                take_profit_price=current - risk_distance * 2.2,
                regime=regime,
                indicators=indicators,
                model_score=score,
                ai_probability=ai_probability,
                reason=f"ensemble SELL: trend+momentum+RSI+volume+ML; regime={regime.value}",
            )
        return AdaptiveDecision(
            Signal.HOLD,
            confidence,
            regime=regime,
            indicators=indicators,
            model_score=score,
            ai_probability=ai_probability,
            reason="ensemble score below entry threshold",
        )
