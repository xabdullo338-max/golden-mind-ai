import httpx
from fastapi import FastAPI, HTTPException, Query

from app.strategy import generate_signal, position_size, risk_levels
from app.risk_manager import RiskManager, RiskConfig

app = FastAPI(
    title="GOLDEN MIND AI",
    description="Binance Spot market scanner with paper-trading safety layer",
    version="1.2.0",
)

BINANCE_URL = "https://api.binance.com"
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"}
risk_manager = RiskManager(RiskConfig())


def calculate_ema(prices: list[float], period: int):
    if len(prices) < period:
        return None

    alpha = 2 / (period + 1)
    ema = sum(prices[:period]) / period

    for price in prices[period:]:
        ema = price * alpha + ema * (1 - alpha)

    return round(ema, 8)


def calculate_rsi(prices: list[float], period: int = 14):
    if len(prices) < period + 1:
        return None

    changes = [
        prices[i] - prices[i - 1]
        for i in range(len(prices) - period, len(prices))
    ]

    gains = sum(max(change, 0) for change in changes) / period
    losses = sum(max(-change, 0) for change in changes) / period

    if losses == 0:
        return 100.0 if gains > 0 else 50.0

    rs = gains / losses
    return round(100 - (100 / (1 + rs)), 2)


async def fetch_market(symbol: str):
    symbol = symbol.upper()

    if symbol not in ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol not allowed. Use one of: {sorted(ALLOWED_SYMBOLS)}",
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            ticker_response = await client.get(
                f"{BINANCE_URL}/api/v3/ticker/24hr",
                params={"symbol": symbol},
            )
            ticker_response.raise_for_status()

            candle_response = await client.get(
                f"{BINANCE_URL}/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": "1m",
                    "limit": 100,
                },
            )
            candle_response.raise_for_status()

        ticker = ticker_response.json()
        candles = candle_response.json()
        prices = [float(candle[4]) for candle in candles]

        return {
            "symbol": symbol,
            "price": float(ticker["lastPrice"]),
            "change_24h": float(ticker["priceChangePercent"]),
            "volume_24h": float(ticker["quoteVolume"]),
            "indicators": {
                "EMA_20": calculate_ema(prices, 20),
                "EMA_50": calculate_ema(prices, 50),
                "RSI_14": calculate_rsi(prices, 14),
            },
        }

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Binance HTTP error: {exc.response.status_code}",
        )
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Binance connection error")


@app.get("/")
async def home():
    return {
        "project": "GOLDEN MIND AI",
        "status": "running",
        "version": "1.2.0",
        "mode": "PAPER",
        "live_trading": False,
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "live_trading": False}


@app.get("/api/v1/market/{symbol}")
async def market(symbol: str):
    return await fetch_market(symbol)


@app.get("/api/v1/signal/{symbol}")
async def signal(
    symbol: str,
    balance_usdt: float = Query(100.0, gt=0),
    risk_pct: float = Query(1.0, gt=0, le=2.0),
):
    market_data = await fetch_market(symbol)
    indicators = market_data["indicators"]

    signal_value = generate_signal(
        ema20=indicators["EMA_20"],
        ema50=indicators["EMA_50"],
        rsi14=indicators["RSI_14"],
    )

    levels = risk_levels(market_data["price"], signal_value)

    quantity = position_size(
        balance_usdt=balance_usdt,
        entry_price=market_data["price"],
        risk_pct=risk_pct,
    )

    valid, risk_message = risk_manager.validate(
        balance=balance_usdt,
        quantity=quantity,
        entry_price=market_data["price"],
    )

    return {
        "project": "GOLDEN MIND AI",
        "mode": "PAPER",
        "symbol": market_data["symbol"],
        "price": market_data["price"],
        "signal": signal_value,
        "indicators": indicators,
        "risk": {
            **levels,
            "risk_pct": risk_pct,
            "suggested_quantity": quantity,
            "risk_check": risk_message,
            "risk_approved": valid,
        },
        "live_order_sent": False,
    }
