# GOLDEN MIND AI

Safety-first algorithmic trading foundation.

## Current status

**PAPER ONLY. Live orders are disabled.** This repository is intentionally built so that a broker integration cannot silently place real orders.

### Architecture
- FastAPI API
- Market-data adapter
- Signal/strategy layer
- Risk engine with per-trade and daily-loss limits
- Paper broker
- Backtesting foundation
- Automated tests
- Configuration through environment variables

### Risk defaults
- Initial paper balance: $300
- Max risk per trade: 1%
- Max daily loss: 3%
- Max open positions: 3
- Live trading: disabled

### Local run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run tests:
```bash
pytest -q
```

## Broker roadmap
1. Validate strategy with historical backtests.
2. Run paper trading for a meaningful sample.
3. Add an IBKR adapter using the official API.
4. Keep live execution behind an explicit kill switch.
5. Start with a small allocation only after validation.

**Never commit API keys, broker credentials, or secrets.**
