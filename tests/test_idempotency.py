import pytest
from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter

class Fake(BrokerAdapter):
    def __init__(self):
        self.account = BrokerAccount("A", "TEST", "PAPER")
        self.calls = 0

    async def get_balance(self): return {"USD": 1000}
    async def get_positions(self): return []
    async def get_open_orders(self): return []
    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        self.calls += 1
        return {"status": "PAPER", "calls": self.calls}

    async def cancel_order(self, symbol, order_id): return {"status": "CANCELLED"}

@pytest.mark.asyncio
async def test_duplicate_order_is_rejected():
    manager = AccountManager()
    broker = Fake()
    manager.register(broker)
    router = OrderRouter(manager)
    order = OrderRequest("same-id", "BTCUSDT", OrderSide.BUY, 0.01)

    first = await router.route("A", order)
    assert first["status"] == "PAPER"

    with pytest.raises(RuntimeError, match="duplicate client order id"):
        await router.route("A", order)

    assert broker.calls == 1
