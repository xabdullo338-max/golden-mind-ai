from app.trade_rate_limiter import TradeRateLimiter
from app.scalping_filter import ScalpingFilter, ScalpingFilterConfig

def test_hourly_limit():
    limiter = TradeRateLimiter(max_trades_per_hour=2)
    assert limiter.check().allowed
    limiter.record()
    limiter.record()
    assert not limiter.check().allowed

def test_scalping_filter_rejects_small_move():
    f = ScalpingFilter(ScalpingFilterConfig(min_move_pct=0.1))
    assert not f.accept(100, 99.98)

def test_scalping_filter_accepts_move_and_spread():
    f = ScalpingFilter(ScalpingFilterConfig(min_move_pct=0.1, max_spread_pct=0.08))
    assert f.accept(100.2, 100, 100.15, 100.20)
