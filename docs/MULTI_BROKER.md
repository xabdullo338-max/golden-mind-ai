# Golden Mind AI — Multi-Broker Architecture

Golden Mind AI uses a broker-adapter boundary so one strategy/order model can route to different brokers and accounts.

## Current status
- PAPER mode is the default.
- Binance and IBKR adapters exist as isolated integration boundaries.
- AccountManager supports independent account IDs, enable/disable state, targeted orders, and broadcast orders.
- Live execution is intentionally disabled.
- Credentials must come from environment/secret management, never Git.

## Account isolation
Each account should have its own:
- credentials/session
- risk limits
- strategy allocation
- capital allocation
- order/fill journal
- kill switch

## Planned broker adapters
Binance → Spot/Testnet first.
IBKR → Paper API first.
Future adapters can implement the same BrokerAdapter interface.

## Routing examples
- Strategy A → BINANCE-01
- Strategy B → IBKR-01
- Strategy C → BINANCE-01 + IBKR-01
- Emergency stop → disable account or global trading switch

## Safety gates
1. Backtest
2. Broker paper/testnet
3. Reconciliation and failure tests
4. Small live allocation
5. Gradual expansion

Never put API keys, API secrets, or private keys in GitHub.
