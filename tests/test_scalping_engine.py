from datetime import datetime, timezone

from app.market_data import MarketTick
from app.scalping_engine import ScalpingEngine, ScalpingEngineConfig
from app.order_models import OrderSide

def test_tick_spread():
    tick = MarketTick("BINANCE", "BTCUSDT", 100, datetime.now(timezone.utc), 99.95, 100.05)
    assert tick.spread_bps > 0

def test_engine_generates_signal():
    engine = ScalpingEngine(ScalpingEngineConfig(min_move_pct=0.01))
    tick = MarketTick("BINANCE", "BTCUSDT", 100.2, datetime.now(timezone.utc), 100.15, 100.20)
    signal = engine.generate("BINANCE-01", tick, 100)
    assert signal is not None
    assert signal.side == OrderSide.BUY

def test_engine_respects_hourly_limit():
    engine = ScalpingEngine(ScalpingEngineConfig(max_trades_per_hour=1))
    assert engine.can_submit("A")
    engine.record_submission("A")
    assert not engine.can_submit("A")
