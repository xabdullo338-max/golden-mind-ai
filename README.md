# GOLDEN MIND AI

A safety-first Binance Spot market scanner and paper-trading foundation.

## Current mode

**PAPER ONLY. Live Binance orders are disabled.**

The first version uses:
- EMA 20 / EMA 50
- RSI 14
- BUY / SELL / HOLD signal
- Stop-loss / take-profit levels
- Position sizing
- Risk validation
- Binance public market data

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API

```text
GET /
GET /health
GET /api/v1/market/BTCUSDT
GET /api/v1/signal/BTCUSDT
```

Example:

```text
http://127.0.0.1:8000/api/v1/signal/BTCUSDT
```

## Security

Do not upload `.env` or real Binance API keys to GitHub.

For future live trading, create a Binance API key with **withdrawals disabled** and use the minimum permissions required. Live trading should only be enabled after backtesting and paper-trading validation.

## Roadmap

1. Market data
2. Strategy engine
3. Risk manager
4. Paper trader
5. Backtester
6. Dashboard
7. Binance Testnet
8. Live Spot execution (optional, after validation)
