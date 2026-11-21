import pytest

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.execution_gate import ExecutionGate
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter
from app.portfolio_state import PortfolioStateManager
from app.execution_ledger import ExecutionLedger
from app.idempotency import OrderIdempotencyGuard


class FakeAdapter(BrokerAdapter):
    def __init__(self, mode: str):
        self.account = BrokerAccount("A", "TEST", mode)

    async def get_balance(self):
        return {"USDT": 1000.0}

    async def get_positions(self):
        return []

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status": "FILLED", "symbol": symbol, "side": side, "executedQty": quantity}

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


def test_execution_delta_uses_cumulative_quantity():
    ledger = ExecutionLedger()
    assert ledger.delta("1", 2.0) == 2.0
    assert ledger.delta("1", 2.0) == 0.0
    assert ledger.delta("1", 3.5) == 1.5


def test_idempotency_guard_rejects_duplicate():
    guard = OrderIdempotencyGuard()
    assert guard.check_and_mark("gmai-1").allowed
    assert not guard.check_and_mark("gmai-1").allowed


@pytest.mark.asyncio
async def test_testnet_order_requires_reconciled_state():
    manager = AccountManager()
    manager.register(FakeAdapter("TESTNET"))
    state = PortfolioStateManager()
    router = OrderRouter(manager, execution_gate=ExecutionGate(), portfolio_state=state)

    with pytest.raises(RuntimeError, match="Broker state is not reconciled"):
        await router.route("A", OrderRequest("t1", "BTCUSDT", OrderSide.BUY, 0.001))


@pytest.mark.asyncio
async def test_testnet_order_allowed_after_reconciliation():
    manager = AccountManager()
    manager.register(FakeAdapter("TESTNET"))
    state = PortfolioStateManager()
    state.reconcile("A", "TEST", {"USDT": 1000.0}, [])
    router = OrderRouter(manager, execution_gate=ExecutionGate(), portfolio_state=state)

    result = await router.route("A", OrderRequest("t2", "BTCUSDT", OrderSide.BUY, 0.001))
    assert result["status"] == "FILLED"


@pytest.mark.asyncio
async def test_live_order_is_blocked_even_if_adapter_exists(monkeypatch):
    monkeypatch.setenv("GMAI_LIVE_TRADING", "true")
    manager = AccountManager()
    manager.register(FakeAdapter("LIVE"))
    state = PortfolioStateManager()
    state.reconcile("A", "TEST", {"USDT": 1000.0}, [])
    router = OrderRouter(manager, execution_gate=ExecutionGate(), portfolio_state=state)

    with pytest.raises(RuntimeError, match="Live execution is not enabled"):
        await router.route("A", OrderRequest("live1", "BTCUSDT", OrderSide.BUY, 0.001))
