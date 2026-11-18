from datetime import UTC, datetime, timedelta

import pytest

from app.market_data import MarketTick
from app.market_data_guard import MarketDataFreshnessGuard


def test_fresh_tick_is_allowed():
    now = datetime.now(UTC)
    tick = MarketTick("BINANCE", "BTCUSDT", 60000, now)
    assert MarketDataFreshnessGuard(2.0).is_fresh(tick, now=now)


def test_stale_tick_is_rejected():
    now = datetime.now(UTC)
    tick = MarketTick("BINANCE", "BTCUSDT", 60000, now - timedelta(seconds=2.1))
    guard = MarketDataFreshnessGuard(2.0)
    assert not guard.is_fresh(tick, now=now)
    with pytest.raises(RuntimeError, match="stale market data"):
        guard.assert_fresh(tick, now=now)


def test_future_tick_is_rejected():
    now = datetime.now(UTC)
    tick = MarketTick("BINANCE", "BTCUSDT", 60000, now + timedelta(seconds=1))
    assert not MarketDataFreshnessGuard(2.0).is_fresh(tick, now=now)
