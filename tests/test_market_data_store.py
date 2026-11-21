from datetime import datetime, timedelta, timezone

import pytest

from app.market_data import MarketTick
from app.market_data_store import MarketDataStore


def test_market_data_store_exposes_price_and_age():
    store = MarketDataStore()
    now = datetime.now(timezone.utc)
    store.update(MarketTick("BINANCE", "BTCUSDT", 30000.0, now))
    assert store.price_map("BINANCE")["BTC"] == 30000.0
    assert store.age_seconds("BINANCE", "BTCUSDT", now=now) == 0.0


def test_market_data_store_rejects_stale_tick():
    store = MarketDataStore()
    old = datetime.now(timezone.utc) - timedelta(seconds=3)
    store.update(MarketTick("BINANCE", "BTCUSDT", 30000.0, old))
    with pytest.raises(RuntimeError, match="market data is stale"):
        store.require_fresh("BINANCE", "BTCUSDT", 2.0)


def test_market_data_store_rejects_missing_tick():
    store = MarketDataStore()
    with pytest.raises(RuntimeError, match="market data unavailable"):
        store.require_fresh("BINANCE", "BTCUSDT", 2.0)
