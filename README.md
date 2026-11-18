# GOLDEN MIND AI

Safety-first algorithmic trading foundation.

## Current status

**PAPER / TESTNET / DEMO foundation. LIVE execution remains disabled by default.**

The production application entrypoint is `app.main:app`, which imports the unified authenticated API from `app.api`.

### Architecture
- FastAPI authenticated API
- Multi-account broker abstraction
- Account-scoped order routing
- Kill switch and execution gate
- Broker-state reconciliation and reconnect recovery
- Durable account/broker-scoped order journal
- Binance WebSocket execution-event bridge
- Market-data freshness guard
- Scalping signal engine with trade-rate ceiling
- Risk engine with per-trade and daily-loss limits
- Paper broker foundation
- Automated tests

### Risk defaults
- Initial paper balance: $300
- Max risk per trade: 0.25%
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

### Safety model

New order execution is blocked when:
- the account is disabled;
- the global kill switch is active;
- broker state has not been reconciled;
- the daily-loss gate fails;
- a duplicate client order ID is detected.

After a broker WebSocket disconnect, the account is marked unconfirmed. Reconciliation must succeed before execution can resume.

### Broker roadmap
1. Validate strategy with historical backtests.
2. Run paper trading for a meaningful sample.
3. Complete Binance TESTNET end-to-end verification.
4. Validate IBKR DEMO using the official current API.
5. Keep LIVE execution behind an explicit, authenticated safety mechanism.
6. Start with a small allocation only after validation.

**Never commit API keys, broker credentials, or secrets.**
