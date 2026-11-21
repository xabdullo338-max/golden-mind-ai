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



@pytest.mark.asyncio
async def test_account_emergency_freeze_cancels_open_orders_and_emits_audit():
    from app.event_bus import EventBus
    from app.kill_switch import EmergencySafetySystem

    class EmergencyAdapter(SafetyAdapter):
        def __init__(self):
            super().__init__()
            self.open_orders = [
                {"symbol": "BTCUSDT", "orderId": "101", "status": "NEW"},
                {"symbol": "ETHUSDT", "orderId": "102", "status": "NEW"},
            ]
            self.cancelled = []

        async def get_open_orders(self, symbol=None):
            return list(self.open_orders)

        async def cancel_order(self, symbol, order_id):
            self.cancelled.append(f"{symbol}:{order_id}")
            return {"status": "CANCELED"}

    manager = AccountManager()
    adapter = EmergencyAdapter()
    manager.register(adapter)
    events = EventBus()
    safety = EmergencySafetySystem(manager, KillSwitch(), events)

    queue = events.subscribe()
    await safety.freeze_account("A", "websocket disconnected")

    assert safety.is_frozen("A")
    assert adapter.cancelled == ["BTCUSDT:101", "ETHUSDT:102"]

    event_types = []
    while not queue.empty():
        event_types.append((await queue.get()).event_type)
    assert "EMERGENCY_CANCEL_ALL" in event_types
    assert "EMERGENCY_ACCOUNT_FROZEN" in event_types


@pytest.mark.asyncio
async def test_repeated_broker_rejections_trigger_circuit_breaker():
    from app.kill_switch import EmergencySafetySystem

    manager = AccountManager()
    manager.register(SafetyAdapter())
    safety = EmergencySafetySystem(manager, KillSwitch(), rejection_threshold=3)

    assert not await safety.record_rejection("A", "reject-1")
    assert not await safety.record_rejection("A", "reject-2")
    assert await safety.record_rejection("A", "reject-3")
    assert safety.is_frozen("A")


@pytest.mark.asyncio
async def test_emergency_recovery_unfreezes_account():
    from app.kill_switch import EmergencySafetySystem

    manager = AccountManager()
    manager.register(SafetyAdapter())
    safety = EmergencySafetySystem(manager, KillSwitch())

    await safety.freeze_account("A", "test")
    assert safety.is_frozen("A")

    await safety.recover_account("A")
    assert not safety.is_frozen("A")
