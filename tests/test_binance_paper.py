import pytest
from app.brokers.binance import BinanceAdapter, BinanceAPIError

@pytest.mark.asyncio
async def test_binance_paper_buy_and_sell():
    broker = BinanceAdapter("PAPER-01", mode="PAPER", initial_quote_balance=300)
    buy = await broker.place_order("BTCUSDT", "BUY", 0.001, price=60000, client_order_id="b1")
    assert buy["status"] == "FILLED"
    assert (await broker.get_balance())["USDT"] == pytest.approx(240.0)
    sell = await broker.place_order("BTCUSDT", "SELL", 0.001, price=61000, client_order_id="s1")
    assert sell["status"] == "FILLED"
    assert (await broker.get_balance())["USDT"] == pytest.approx(301.0)

@pytest.mark.asyncio
async def test_binance_paper_rejects_insufficient_cash():
    broker = BinanceAdapter("PAPER-01", mode="PAPER", initial_quote_balance=10)
    with pytest.raises(BinanceAPIError, match="Insufficient PAPER balance"):
        await broker.place_order("BTCUSDT", "BUY", 1, price=60000)

@pytest.mark.asyncio
async def test_binance_paper_rejects_insufficient_position():
    broker = BinanceAdapter("PAPER-01", mode="PAPER", initial_quote_balance=300)
    with pytest.raises(BinanceAPIError, match="Insufficient PAPER position"):
        await broker.place_order("BTCUSDT", "SELL", 0.001, price=60000)

@pytest.mark.asyncio
async def test_binance_live_requires_explicit_flag(monkeypatch):
    monkeypatch.delenv("GMAI_LIVE_TRADING", raising=False)
    broker = BinanceAdapter("LIVE-01", mode="LIVE", api_key="k", api_secret="s")
    with pytest.raises(BinanceAPIError, match="Execution is disabled"):
        await broker.place_order("BTCUSDT", "BUY", 0.001, price=60000)
