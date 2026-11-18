from app.binance_market_data import BinanceMarketDataStream, BinanceMarketStreamConfig

def test_stream_url_contains_book_ticker():
    stream = BinanceMarketDataStream(
        BinanceMarketStreamConfig(symbols=("btcusdt", "ethusdt"))
    )
    url = stream.stream_url()
    assert "btcusdt@bookTicker" in url
    assert "ethusdt@bookTicker" in url

def test_normalize_book_ticker():
    tick = BinanceMarketDataStream._normalize({
        "stream": "btcusdt@bookTicker",
        "data": {"s":"BTCUSDT", "b":"100.0", "a":"100.2"}
    })
    assert tick is not None
    assert tick.symbol == "BTCUSDT"
    assert tick.bid == 100.0
    assert tick.ask == 100.2
    assert tick.price == 100.1
