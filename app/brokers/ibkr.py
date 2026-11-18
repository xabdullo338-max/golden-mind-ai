from .base import BrokerAdapter, BrokerAccount

class IBKRAdapter(BrokerAdapter):
    """Adapter boundary for IBKR Web/TWS API. Live execution remains disabled by default."""
    def __init__(self, account_id: str, mode: str = "PAPER"):
        self.account = BrokerAccount(account_id, "IBKR", mode)

    async def get_balance(self):
        raise NotImplementedError("IBKR transport/auth layer will be wired to the selected API.")

    async def get_positions(self):
        raise NotImplementedError("IBKR transport/auth layer will be wired to the selected API.")

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        if self.account.mode != "LIVE":
            return {"status": "PAPER", "broker": "IBKR", "symbol": symbol, "side": side, "quantity": quantity}
        raise NotImplementedError("Live IBKR execution is disabled until validation and explicit enablement.")

    async def cancel_order(self, symbol, order_id):
        raise NotImplementedError
