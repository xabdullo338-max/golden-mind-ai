from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from .market_data import MarketTick
from .order_models import OrderSide
from .scalping_filter import ScalpingFilter
from .trade_rate_limiter import TradeRateLimiter
from .market_data_guard import MarketDataFreshnessGuard

@dataclass(frozen=True)
class ScalpingEngineConfig:
    min_move_pct: float = 0.03
    max_spread_pct: float = 0.08
    cooldown_seconds: float = 0.5
    max_trades_per_hour: int = 100
    allow_short: bool = False
    max_market_data_age_seconds: float = 2.0

@dataclass(frozen=True)
class ScalpingSignal:
    symbol: str
    side: OrderSide
    price: float
    edge_pct: float
    reason: str
    timestamp: datetime

class ScalpingEngine:
    """Signal generator. It never trades merely to hit a trade-count target."""

    def __init__(self, config: ScalpingEngineConfig | None = None):
        self.config = config or ScalpingEngineConfig()
        self.filter = ScalpingFilter(config=self._filter_config())
        self.limiters: dict[str, TradeRateLimiter] = {}
        self.freshness = MarketDataFreshnessGuard(self.config.max_market_data_age_seconds)

    def _filter_config(self):
        from .scalping_filter import ScalpingFilterConfig
        return ScalpingFilterConfig(min_move_pct=self.config.min_move_pct,
                                    max_spread_pct=self.config.max_spread_pct)

    def limiter(self, account_id: str) -> TradeRateLimiter:
        if account_id not in self.limiters:
            self.limiters[account_id] = TradeRateLimiter(
                max_trades_per_hour=self.config.max_trades_per_hour,
                cooldown_seconds=self.config.cooldown_seconds)
        return self.limiters[account_id]

    def generate(self, account_id: str, tick: MarketTick,
                 reference_price: float) -> ScalpingSignal | None:
        if reference_price <= 0 or tick.price <= 0:
            return None
        if not self.freshness.is_fresh(tick):
            return None
        if not self.filter.accept(tick.price, reference_price, tick.bid, tick.ask):
            return None
        edge_pct = (tick.price - reference_price) / reference_price * 100
        if edge_pct < 0 and not self.config.allow_short:
            return None
        side = OrderSide.BUY if edge_pct > 0 else OrderSide.SELL
        return ScalpingSignal(tick.symbol, side, tick.price, abs(edge_pct),
                              "momentum_scalp", tick.timestamp)
    
    def can_submit(self, account_id: str) -> bool:
        return self.limiter(account_id).check().allowed

    def record_submission(self, account_id: str) -> None:
        self.limiter(account_id).record()
