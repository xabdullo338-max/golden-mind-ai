# Scalping market-data pipeline

The Binance public book-ticker stream feeds normalized MarketTick objects into the scalping pipeline.

Flow:

Binance bookTicker -> MarketTick -> ScalpingEngine -> Risk -> OrderRouter

The stream uses public market data only; API credentials are not required for this feed.

Reconnects are automatic. Live order execution remains separately guarded by the existing execution/security gates.

## Example

    stream = BinanceMarketDataStream(
        BinanceMarketStreamConfig(symbols=("btcusdt", "ethusdt"))
    )
    await stream.start(handler)
