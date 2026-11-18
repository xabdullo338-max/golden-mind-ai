# Binance Spot execution foundation

Golden Mind AI now has a signed Binance Spot HTTP adapter.

## Modes
- PAPER: no broker request is sent.
- TESTNET: signed requests go to Binance Spot Testnet.
- LIVE: production requests require GMAI_LIVE_TRADING=true.

## Environment
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_BASE_URL=https://testnet.binance.vision
GMAI_LIVE_TRADING=false

Never commit credentials to GitHub.