import pytest

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.execution_gate import ExecutionGate
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter
from app.portfolio_state import PortfolioStateManager
from app.risk import AccountSnapshot, DailyLossGuard


class FakeBroker(BrokerAdapter):
    def __init__(self, account_id="A", mode="PAPER"):
        self.account = BrokerAccount(account_id, "TEST", mode)

    async def get_balance(self):
        return {"USD": 1000}

    async def get_positions(self):
        return []

    async def get_open_orders(self, symbol=None):
        return []

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status": "PAPER"}

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


@pytest.mark.asyncio
async def test_router_blocks_unconfirmed_account():
    manager = AccountManager()
    manager.register(FakeBroker())
    state = PortfolioStateManager()
    router = OrderRouter(
        manager,
        execution_gate=ExecutionGate(),
        portfolio_state=state,
    )

    with pytest.raises(RuntimeError, match="Broker state is not reconciled"):
        await router.route(
            "A",
            OrderRequest("cid-1", "BTCUSDT", OrderSide.BUY, 0.01),
        )


def test_live_daily_loss_requires_snapshot():
    manager = AccountManager()
    manager.register(FakeBroker(mode="LIVE"))
    router = OrderRouter(
        manager,
        daily_loss_guard=DailyLossGuard(3.0),
        snapshot_provider=None,
    )

    assert router._daily_loss_ok("A", live=True) is False


def test_live_daily_loss_uses_snapshot():
    manager = AccountManager()
    manager.register(FakeBroker(mode="LIVE"))
    snapshot = AccountSnapshot(
        account_id="A",
        equity=970.0,
        cash=970.0,
        realized_pnl=-30.0,
        unrealized_pnl=0.0,
        daily_start_equity=1000.0,
        open_positions=0,
    )
    router = OrderRouter(
        manager,
        daily_loss_guard=DailyLossGuard(3.0),
        snapshot_provider=lambda account_id: snapshot,
    )

    assert router._daily_loss_ok("A", live=True) is False
