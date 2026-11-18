import pytest
from datetime import datetime, timezone
from app.market_data import MarketTick
from app.strategy import StrategyEngine

def test_tick_rejects_invalid_price():
    with pytest.raises(ValueError):
        MarketTick("BINANCE", "BTCUSDT", 0, datetime.now(timezone.utc))

def test_strategy_returns_buy_when_fast_is_above_slow():
    tick = MarketTick("BINANCE", "BTCUSDT", 100, datetime.now(timezone.utc))
    signal = StrategyEngine().generate(tick, 101, 100)
    assert signal is not None
    assert signal.side.value == "BUY"

def test_strategy_does_not_create_zero_quantity_order():
    tick = MarketTick("BINANCE", "BTCUSDT", 100, datetime.now(timezone.utc))
    signal = StrategyEngine().generate(tick, 101, 100)
    with pytest.raises(ValueError):
        StrategyEngine().to_order(signal, "x")