import pytest

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.execution_gate import ExecutionGate
from app.idempotency import OrderIdempotencyGuard
from app.kill_switch import KillSwitch
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter
from app.portfolio_state import PortfolioStateManager


class SafetyAdapter(BrokerAdapter):
    def __init__(self, account_id: str = "A", mode: str = "TESTNET"):
        self.account = BrokerAccount(account_id, "TEST", mode)
        self.place_calls = 0

    async def get_balance(self):
        return {"USDT": 1000.0}

    async def get_positions(self):
        return []

    async def place_order(
        self, symbol, side, quantity, order_type="MARKET", **kwargs
    ):
        self.place_calls += 1
        return {
            "status": "FILLED",
            "symbol": symbol,
            "side": side,
            "executedQty": quantity,
        }

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


def build_confirmed_router():
    manager = AccountManager()
    adapter = SafetyAdapter()
    manager.register(adapter)

    state = PortfolioStateManager()
    state.reconcile("A", "TEST", {"USDT": 1000.0}, [])
    router = OrderRouter(
        manager,
        execution_gate=ExecutionGate(),
        portfolio_state=state,
        idempotency=OrderIdempotencyGuard(),
    )
    return router, adapter, state


@pytest.mark.asyncio
async def test_global_kill_switch_blocks_before_broker_call():
    router, adapter, _ = build_confirmed_router()
    router.kill_switch.stop_all()

    with pytest.raises(RuntimeError, match="Global kill switch is active"):
        await router.route(
            "A", OrderRequest("kill-1", "BTCUSDT", OrderSide.BUY, 0.001)
        )

    assert adapter.place_calls == 0


@pytest.mark.asyncio
async def test_duplicate_client_order_id_never_reaches_broker_twice():
    router, adapter, _ = build_confirmed_router()
    order = OrderRequest("dup-1", "BTCUSDT", OrderSide.BUY, 0.001)

    first = await router.route("A", order)
    assert first["status"] == "FILLED"
    assert adapter.place_calls == 1

    with pytest.raises(RuntimeError, match="duplicate client order id"):
        await router.route("A", order)

    assert adapter.place_calls == 1


@pytest.mark.asyncio
async def test_disconnect_marks_state_unconfirmed_and_blocks_new_order():
    router, adapter, state = build_confirmed_router()
    assert state.is_confirmed("A")

    state.mark_unconfirmed("A", "TEST")
    assert not state.is_confirmed("A")

    with pytest.raises(RuntimeError, match="Broker state is not reconciled"):
        await router.route(
            "A", OrderRequest("disconnect-1", "BTCUSDT", OrderSide.BUY, 0.001)
        )

    assert adapter.place_calls == 0


@pytest.mark.asyncio
async def test_reconciliation_restores_order_permission_after_disconnect():
    router, adapter, state = build_confirmed_router()
    state.mark_unconfirmed("A", "TEST")

    with pytest.raises(RuntimeError, match="Broker state is not reconciled"):
        await router.route(
            "A", OrderRequest("recovery-1", "BTCUSDT", OrderSide.BUY, 0.001)
        )

    state.reconcile("A", "TEST", {"USDT": 999.0}, [])
    assert state.is_confirmed("A")

    result = await router.route(
        "A", OrderRequest("recovery-2", "BTCUSDT", OrderSide.BUY, 0.001)
    )
    assert result["status"] == "FILLED"
    assert adapter.place_calls == 1
