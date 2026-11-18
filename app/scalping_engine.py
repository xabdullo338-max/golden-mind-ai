from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from .market_data import MarketTick
from .order_models import OrderSide
from .scalping_filter import ScalpingFilter
from .trade_rate_limiter import TradeRateLimiter

@dataclass(frozen=True)
class ScalpingEngineConfig:
    min_move_pct: float = 0.03
    max_spread_pct: float = 0.08
    cooldown_seconds: float = 0.5
    max_trades_per_hour: int = 100

@dataclass(frozen=True)
class ScalpingSignal:
    symbol: str
    side: OrderSide
    price: float
    edge_pct: float
    reason: str
    timestamp: datetime

class ScalpingEngine:
    """Generates opportunities; it never forces a trade just to hit the hourly target."""

    def __init__(self, config: ScalpingEngineConfig | None = None):
        self.config = config or ScalpingEngineConfig()
        self.filter = ScalpingFilter(
            config=self._filter_config()
        )
        self.limiters: dict[str, TradeRateLimiter] = {}

    def _filter_config(self):
        from .scalping_filter import ScalpingFilterConfig
        return ScalpingFilterConfig(
            min_move_pct=self.config.min_move_pct,
            max_spread_pct=self.config.max_spread_pct,
        )

    def limiter(self, account_id: str) -> TradeRateLimiter:
        if account_id not in self.limiters:
            self.limiters[account_id] = TradeRateLimiter(
                max_trades_per_hour=self.config.max_trades_per_hour,
                cooldown_seconds=self.config.cooldown_seconds,
            )
        return self.limiters[account_id]

    def generate(self, account_id: str, tick: MarketTick,
                 reference_price: float) -> ScalpingSignal | None:
        if not self.filter.accept(
            tick.price, reference_price, tick.bid, tick.ask
        ):
            return None

        edge_pct = (tick.price - reference_price) / reference_price * 100
        side = OrderSide.BUY if edge_pct > 0 else OrderSide.SELL
        return ScalpingSignal(
            symbol=tick.symbol,
            side=side,
            price=tick.price,
            edge_pct=abs(edge_pct),
            reason="momentum_scalp",
            timestamp=tick.timestamp,
        )

    def can_submit(self, account_id: str) -> bool:
        return self.limiter(account_id).check().allowed

    def record_submission(self, account_id: str) -> None:
        self.limiter(account_id).record()
