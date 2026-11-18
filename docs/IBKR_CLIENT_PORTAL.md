# IBKR Client Portal foundation

IBKR provides both a Python TWS API and a RESTful Client Portal API. Golden Mind AI uses a broker adapter so the strategy/risk layers stay broker-independent.

## Current implementation
- PAPER mode: no IBKR request is sent.
- Non-PAPER mode: requests target the configured Client Portal Gateway.
- Authentication is represented by the gateway session cookie; the robot does not store an IBKR password.
- Orders require an IBKR contract ID (`conid`).

IBKR official documentation covers both Python TWS API and Client Portal API, including gateway authentication, market data and order placement.