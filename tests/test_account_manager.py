import pytest
from app.account_manager import AccountManager
from app.order_models import OrderRequest, OrderSide
from app.brokers.base import BrokerAccount, BrokerAdapter

class FakeAdapter(BrokerAdapter):
    def __init__(self, account_id, broker):
        self.account = BrokerAccount(account_id, broker, "PAPER")
        self.orders = []

    async def get_balance(self):
        return {"USD": 1000.0}

    async def get_positions(self):
        return []

    async def get_open_orders(self):
        return []

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        self.orders.append((symbol, side, quantity, order_type, kwargs))
        return {"status": "PAPER", "account_id": self.account.account_id, "symbol": symbol}

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELLED", "order_id": order_id}

@pytest.mark.asyncio
async def test_broadcast_skips_disabled_accounts():
    manager = AccountManager()
    a = FakeAdapter("BINANCE-01", "BINANCE")
    b = FakeAdapter("IBKR-01", "IBKR")
    manager.register(a)
    manager.register(b)
    manager.disable("IBKR-01")
    order = OrderRequest("test-001", "BTCUSDT", OrderSide.BUY, 0.01)
    result = await manager.broadcast_order(order)
    assert len(result) == 1
    assert a.orders[0][0] == "BTCUSDT"

@pytest.mark.asyncio
async def test_targeted_order():
    manager = AccountManager()
    a = FakeAdapter("BINANCE-01", "BINANCE")
    b = FakeAdapter("IBKR-01", "IBKR")
    manager.register(a)
    manager.register(b)
    order = OrderRequest("test-002", "AAPL", OrderSide.BUY, 1)
    result = await manager.order_to("IBKR-01", order)
    assert result["account_id"] == "IBKR-01"
    assert len(a.orders) == 0
    assert len(b.orders) == 1
