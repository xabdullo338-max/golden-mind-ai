import pytest
from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.kill_switch import KillSwitch
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter

class Fake(BrokerAdapter):
    def __init__(self):
        self.account = BrokerAccount("A", "TEST", "PAPER")
    async def get_balance(self): return {"USD": 1000}
    async def get_positions(self): return []
    async def get_open_orders(self): return []
    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status": "PAPER"}
    async def cancel_order(self, symbol, order_id): return {"status": "CANCELED"}

@pytest.mark.asyncio
async def test_global_kill_switch_blocks_router():
    manager = AccountManager()
    manager.register(Fake())
    kill = KillSwitch()
    kill.stop_all()
    router = OrderRouter(manager, kill)
    with pytest.raises(RuntimeError, match="Global kill switch"):
        await router.route("A", OrderRequest("k1", "BTCUSDT", OrderSide.BUY, 0.01))
