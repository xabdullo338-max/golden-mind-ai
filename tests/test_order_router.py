import pytest
from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.kill_switch import KillSwitch
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter

class Fake(BrokerAdapter):
    def __init__(self, account_id):
        self.account = BrokerAccount(account_id, "TEST", "PAPER")
    async def get_balance(self): return {"USD": 1000}
    async def get_positions(self): return []
    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status": "PAPER", "account_id": self.account.account_id}
    async def cancel_order(self, symbol, order_id): return {"status": "CANCELLED"}

@pytest.mark.asyncio
async def test_router_blocks_killed_account():
    manager = AccountManager()
    manager.register(Fake("A"))
    kill = KillSwitch()
    kill.disable_account("A")
    router = OrderRouter(manager, kill)
    with pytest.raises(RuntimeError):
        await router.route("A", OrderRequest("x", "BTCUSDT", OrderSide.BUY, 0.01))