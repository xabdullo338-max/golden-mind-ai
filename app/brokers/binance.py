from .base import BrokerAdapter, BrokerAccount

class BinanceAdapter(BrokerAdapter):
    """Adapter boundary for Binance Spot/Testnet. Credentials are never stored in code."""
    def __init__(self, account_id: str, api_key: str, api_secret: str, base_url: str, mode: str = "PAPER"):
        self.account = BrokerAccount(account_id, "BINANCE", mode)
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")

    async def get_balance(self):
        raise NotImplementedError("Binance transport will be implemented behind the broker interface.")

    async def get_positions(self):
        raise NotImplementedError("Binance Spot has balances/orders rather than leveraged positions.")

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        if self.account.mode != "LIVE":
            return {"status": "PAPER", "broker": "BINANCE", "symbol": symbol, "side": side, "quantity": quantity}
        raise NotImplementedError("Live Binance execution is disabled until validation and explicit enablement.")

    async def cancel_order(self, symbol, order_id):
        raise NotImplementedError
