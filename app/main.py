import os
import httpx

from fastapi import FastAPI, HTTPException

app = FastAPI(
    title="GOLDEN MIND AI",
    description="AI-powered Binance Spot Market Scanner",
    version="1.0.0"
)

BINANCE_URL = "https://api.binance.com"

ALLOWED_SYMBOLS = ["BTCUSDT", "ETHUSDT"]


def calculate_ema(prices, period):
    if len(prices) < period:
        return None

    alpha = 2 / (period + 1)
    result = sum(prices[:period]) / period

    for price in prices[period:]:
        result = price * alpha + result * (1 - alpha)

    return round(result, 4)


def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None

    changes = [
        prices[i] - prices[i - 1]
        for i in range(len(prices) - period, len(prices))
    ]

    gains = sum(max(x, 0) for x in changes) / period
    losses = sum(max(-x, 0) for x in changes) / period

    if losses == 0:
        return 100.0 if gains > 0 else 50.0

    rs = gains / losses
    return round(100 - (100 / (1 + rs)), 2)


@app.get("/")
async def home():
    return {
        "project": "GOLDEN MIND AI",
        "status": "running",
        "version": "1.0.0",
        "trading_enabled": False
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "trading_enabled": False
    }


@app.get("/api/v1/market/{symbol}")
async def market_data(symbol: str):

    symbol = symbol.upper()

    if symbol not in ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail="Symbol not allowed"
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:

            ticker_response = await client.get(
                f"{BINANCE_URL}/api/v3/ticker/24hr",
                params={"symbol": symbol}
            )

            ticker_response.raise_for_status()
            ticker = ticker_response.json()

            candle_response = await client.get(
                f"{BINANCE_URL}/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": "1h",
                    "limit": 100
                }
            )

            candle_response.raise_for_status()
            candles = candle_response.json()

        prices = [float(candle[4]) for candle in candles]

        return {
            "project": "GOLDEN MIND AI",
            "symbol": symbol,
            "price": float(ticker["lastPrice"]),
            "change_24h": float(ticker["priceChangePercent"]),
            "volume_24h": float(ticker["quoteVolume"]),
            "indicators": {
                "EMA_20": calculate_ema(prices, 20),
                "EMA_50": calculate_ema(prices, 50),
                "RSI_14": calculate_rsi(prices)
            },
            "trading_enabled": False
        }

    except httpx.HTTPStatusError as exc:
        print(f"BINANCE HTTP ERROR: {exc.response.status_code} - {exc.response.text[:500]}")
        raise HTTPException(
            status_code=502,
            detail="Binance HTTP error. Check Render logs."
        )
    except httpx.RequestError as exc:
        print(f"BINANCE CONNECTION ERROR: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Binance connection error. Check Render logs."
        )
