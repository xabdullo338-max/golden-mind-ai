import pytest

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.event_bus import EventBus
from app.execution_coordinator import ExecutionCoordinator
from app.execution_ledger import ExecutionLedger
from app.execution_gate import ExecutionGate
from app.idempotency import OrderIdempotencyGuard
from app.journal import TradingJournal
from app.kill_switch import EmergencySafetySystem
from app.order_lifecycle import OrderLifecycle, OrderStatus
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter
from app.pending_orders import PendingOrderStore
from app.portfolio_state import PortfolioStateManager
from app.position_engine import PositionEngine
from app.recovery import BrokerRecovery


class TimeoutAdapter(BrokerAdapter):
    def __init__(self, outcome="FILLED", executed_qty=None):
        self.account = BrokerAccount("A", "BINANCE", "TESTNET")
        self.outcome = outcome
        self.executed_qty = executed_qty
        self.place_calls = 0

    async def get_balance(self):
        return {"USDT": 1000.0}

    async def get_positions(self):
        return []

    async def get_open_orders(self, symbol=None):
        return []

    async def get_order_by_client_id(self, symbol, client_order_id):
        if self.outcome is None:
            return None
        return {
            "status": self.outcome,
            "symbol": symbol,
            "side": "BUY",
            "origQty": "0.01",
            "executedQty": str(self.executed_qty if self.executed_qty is not None else (0.01 if self.outcome == "FILLED" else 0)),
            "avgPrice": "100",
            "orderId": "9001",
            "clientOrderId": client_order_id,
        }

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        self.place_calls += 1
        raise TimeoutError("request timed out after broker accepted request")

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


def build_router(adapter, lifecycle, pending):
    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    return OrderRouter(
        accounts,
        execution_gate=ExecutionGate(),
        portfolio_state=state,
        idempotency=OrderIdempotencyGuard(),
        lifecycle=lifecycle,
        pending_orders=pending,
    )


@pytest.mark.asyncio
async def test_timeout_persists_unknown_order_and_never_resubmits():
    adapter = TimeoutAdapter()
    lifecycle = OrderLifecycle()
    pending = PendingOrderStore(":memory:")
    router = build_router(adapter, lifecycle, pending)

    with pytest.raises(RuntimeError, match="outcome is unknown"):
        await router.route("A", OrderRequest(
            "timeout-1", "BTCUSDT", OrderSide.BUY, 0.01
        ))

    assert adapter.place_calls == 1
    assert lifecycle.get("timeout-1", "A", "BINANCE").status is OrderStatus.UNKNOWN
    assert [p.client_order_id for p in pending.list_account("A", "BINANCE")] == ["timeout-1"]

    with pytest.raises(RuntimeError, match="duplicate client order id"):
        await router.route("A", OrderRequest(
            "timeout-1", "BTCUSDT", OrderSide.BUY, 0.01
        ))
    assert adapter.place_calls == 1


@pytest.mark.asyncio
async def test_unknown_order_recovers_to_filled_and_resolves_pending():
    adapter = TimeoutAdapter("FILLED")
    lifecycle = OrderLifecycle()
    pending = PendingOrderStore(":memory:")
    pending.mark(__import__("app.pending_orders", fromlist=["PendingOrder"]).PendingOrder(
        "BINANCE", "A", "fill-1", "BTCUSDT", "BUY", 0.01
    ))
    lifecycle.apply(__import__("app.order_lifecycle", fromlist=["OrderUpdate"]).OrderUpdate(
        broker="BINANCE", account_id="A", client_order_id="fill-1",
        status=OrderStatus.UNKNOWN, symbol="BTCUSDT", side="BUY",
        original_quantity=0.01,
    ))

    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    positions = PositionEngine()
    coordinator = ExecutionCoordinator(
        lifecycle,
        TradingJournal(":memory:"),
        EventBus(),
        positions=positions,
        execution_ledger=ExecutionLedger(":memory:"),
    )
    recovery = BrokerRecovery(
        accounts, state, TradingJournal(":memory:"),
        lifecycle=lifecycle, pending_orders=pending,
        execution_coordinator=coordinator,
    )

    result = await recovery.recover_account("A")
    assert result.confirmed is True
    assert lifecycle.get("fill-1", "A", "BINANCE").status is OrderStatus.FILLED
    assert pending.list_account("A", "BINANCE") == []
    position = positions.get("A", "BTCUSDT")
    assert position is not None
    assert position.quantity == pytest.approx(0.01)
    assert position.average_entry == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_unknown_order_recovers_to_canceled_and_resolves_pending():
    adapter = TimeoutAdapter("CANCELED")
    lifecycle = OrderLifecycle()
    pending = PendingOrderStore(":memory:")
    from app.pending_orders import PendingOrder
    from app.order_lifecycle import OrderUpdate
    pending.mark(PendingOrder("BINANCE", "A", "cancel-1", "BTCUSDT", "BUY", 0.01))
    lifecycle.apply(OrderUpdate(
        broker="BINANCE", account_id="A", client_order_id="cancel-1",
        status=OrderStatus.UNKNOWN, symbol="BTCUSDT", side="BUY",
        original_quantity=0.01,
    ))

    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    recovery = BrokerRecovery(
        accounts, state, TradingJournal(":memory:"),
        lifecycle=lifecycle, pending_orders=pending,
    )

    result = await recovery.recover_account("A")
    assert result.confirmed is True
    assert lifecycle.get("cancel-1", "A", "BINANCE").status is OrderStatus.CANCELED
    assert pending.list_account("A", "BINANCE") == []


@pytest.mark.asyncio
async def test_pending_order_survives_restart_and_blocks_resubmission():
    adapter = TimeoutAdapter("FILLED")
    pending_path = ":memory:"

    pending1 = PendingOrderStore(pending_path)
    from app.pending_orders import PendingOrder
    pending1.mark(PendingOrder("BINANCE", "A", "restart-1", "BTCUSDT", "BUY", 0.01))
    lifecycle1 = OrderLifecycle()
    from app.order_lifecycle import OrderUpdate
    lifecycle1.apply(OrderUpdate(
        broker="BINANCE", account_id="A", client_order_id="restart-1",
        status=OrderStatus.UNKNOWN, symbol="BTCUSDT", side="BUY",
        original_quantity=0.01,
    ))

    # Use a real file for the restart boundary.
    import tempfile
    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    try:
        store = PendingOrderStore(path)
        store.mark(PendingOrder("BINANCE", "A", "restart-1", "BTCUSDT", "BUY", 0.01))

        accounts = AccountManager()
        accounts.register(adapter)
        state = PortfolioStateManager()
        state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
        lifecycle2 = OrderLifecycle()
        recovery = BrokerRecovery(
            accounts, state, TradingJournal(":memory:"),
            lifecycle=lifecycle2, pending_orders=store,
        )
        await recovery.recover_account("A")

        recovered = lifecycle2.get("restart-1", "A", "BINANCE")
        assert recovered is not None
        assert recovered.status is OrderStatus.FILLED
        assert store.list_account("A", "BINANCE") == []

        router = build_router(adapter, lifecycle2, store)
        with pytest.raises(RuntimeError, match="duplicate client order id"):
            await router.route("A", OrderRequest(
                "restart-1", "BTCUSDT", OrderSide.BUY, 0.01
            ))
        assert adapter.place_calls == 0
    finally:
        import os
        os.unlink(path)


@pytest.mark.asyncio
async def test_recovery_failure_freezes_account():
    adapter = TimeoutAdapter()
    async def broken_balance():
        raise RuntimeError("broker unavailable")
    adapter.get_balance = broken_balance

    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    safety = EmergencySafetySystem(accounts, __import__("app.kill_switch", fromlist=["KillSwitch"]).KillSwitch(), EventBus())
    recovery = BrokerRecovery(
        accounts, state, TradingJournal(":memory:"), emergency=safety
    )

    result = await recovery.recover_account("A")
    assert result.confirmed is False
    assert recovery.phase("A").value == "FAILED"
    assert safety.is_frozen("A")


@pytest.mark.asyncio
async def test_unresolved_pending_order_freezes_account_after_recovery():
    adapter = TimeoutAdapter(None)
    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    pending = PendingOrderStore(":memory:")
    from app.pending_orders import PendingOrder
    pending.mark(PendingOrder("BINANCE", "A", "unknown-1", "BTCUSDT", "BUY", 0.01))
    kill_switch = __import__("app.kill_switch", fromlist=["KillSwitch"]).KillSwitch()
    safety = EmergencySafetySystem(accounts, kill_switch, EventBus())
    recovery = BrokerRecovery(
        accounts, state, TradingJournal(":memory:"),
        lifecycle=OrderLifecycle(), pending_orders=pending, emergency=safety
    )

    result = await recovery.recover_account("A")
    assert result.confirmed is False
    assert recovery.phase("A").value == "FAILED"
    assert safety.is_frozen("A")
    assert pending.list_account("A", "BINANCE")


@pytest.mark.asyncio
async def test_frozen_account_blocks_new_order_after_unresolved_recovery():
    adapter = TimeoutAdapter(None)
    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    pending = PendingOrderStore(":memory:")
    from app.pending_orders import PendingOrder
    pending.mark(PendingOrder("BINANCE", "A", "unknown-2", "BTCUSDT", "BUY", 0.01))
    kill_switch = __import__("app.kill_switch", fromlist=["KillSwitch"]).KillSwitch()
    safety = EmergencySafetySystem(accounts, kill_switch, EventBus())
    recovery = BrokerRecovery(
        accounts, state, TradingJournal(":memory:"),
        lifecycle=OrderLifecycle(), pending_orders=pending, emergency=safety
    )

    await recovery.recover_account("A")

    router = OrderRouter(
        accounts,
        kill_switch=kill_switch,
        execution_gate=ExecutionGate(),
        portfolio_state=state,
        pending_orders=pending,
    )
    with pytest.raises(RuntimeError, match="Kill switch is active"):
        await router.route(
            "A", OrderRequest("new-after-freeze", "BTCUSDT", OrderSide.BUY, 0.01)
        )


@pytest.mark.asyncio
async def test_unknown_order_recovers_partial_then_final_fill_without_resubmission():
    adapter = TimeoutAdapter("PARTIALLY_FILLED", executed_qty=0.004)
    lifecycle = OrderLifecycle()
    pending = PendingOrderStore(":memory:")
    from app.pending_orders import PendingOrder
    from app.order_lifecycle import OrderUpdate

    pending.mark(PendingOrder("BINANCE", "A", "partial-1", "BTCUSDT", "BUY", 0.01))
    lifecycle.apply(OrderUpdate(
        broker="BINANCE", account_id="A", client_order_id="partial-1",
        status=OrderStatus.UNKNOWN, symbol="BTCUSDT", side="BUY",
        original_quantity=0.01,
    ))

    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    positions = PositionEngine()
    coordinator = ExecutionCoordinator(
        lifecycle,
        TradingJournal(":memory:"),
        EventBus(),
        positions=positions,
        execution_ledger=ExecutionLedger(":memory:"),
    )
    recovery = BrokerRecovery(
        accounts, state, TradingJournal(":memory:"),
        lifecycle=lifecycle, pending_orders=pending,
        execution_coordinator=coordinator,
    )

    first = await recovery.recover_account("A")
    assert first.confirmed is False
    assert lifecycle.get("partial-1", "A", "BINANCE").status is OrderStatus.PARTIALLY_FILLED
    assert lifecycle.get("partial-1", "A", "BINANCE").executed_quantity == pytest.approx(0.004)
    assert pending.list_account("A", "BINANCE") != []

    adapter.outcome = "FILLED"
    adapter.executed_qty = 0.01
    second = await recovery.recover_account("A")
    assert second.confirmed is True
    recovered = lifecycle.get("partial-1", "A", "BINANCE")
    assert recovered.status is OrderStatus.FILLED
    assert recovered.executed_quantity == pytest.approx(0.01)
    assert pending.list_account("A", "BINANCE") == []
    position = positions.get("A", "BTCUSDT")
    assert position.quantity == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_recovery_and_websocket_fill_reconcile_without_double_count():
    adapter = TimeoutAdapter("FILLED", executed_qty=0.01)
    lifecycle = OrderLifecycle()
    pending = PendingOrderStore(":memory:")
    from app.pending_orders import PendingOrder
    from app.order_lifecycle import OrderUpdate

    pending.mark(PendingOrder("BINANCE", "A", "race-1", "BTCUSDT", "BUY", 0.01))
    lifecycle.apply(OrderUpdate(
        broker="BINANCE", account_id="A", client_order_id="race-1",
        status=OrderStatus.UNKNOWN, symbol="BTCUSDT", side="BUY",
        original_quantity=0.01,
    ))

    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    positions = PositionEngine()
    coordinator = ExecutionCoordinator(
        lifecycle,
        TradingJournal(":memory:"),
        EventBus(),
        positions=positions,
        execution_ledger=ExecutionLedger(":memory:"),
    )
    recovery = BrokerRecovery(
        accounts, state, TradingJournal(":memory:"),
        lifecycle=lifecycle, pending_orders=pending,
        execution_coordinator=coordinator,
    )

    from app.binance_execution_bridge import BinanceExecutionBridge
    bridge = BinanceExecutionBridge("A", coordinator, state, recovery)

    partial_message = {
        "e": "executionReport",
        "X": "PARTIALLY_FILLED",
        "s": "BTCUSDT",
        "c": "race-1",
        "S": "BUY",
        "z": "0.00400000",
        "Z": "0.40000000",
        "l": "0.00400000",
        "L": "100.00000000",
        "i": 9001,
    }

    await __import__("asyncio").gather(
        recovery.recover_account("A"),
        bridge.handle(partial_message),
    )

    position = positions.get("A", "BTCUSDT")
    assert position is not None
    assert position.quantity == pytest.approx(0.01)
    assert lifecycle.get("race-1", "A", "BINANCE").status is OrderStatus.FILLED
    assert pending.list_account("A", "BINANCE") == []


@pytest.mark.asyncio
async def test_ibkr_recovery_and_live_fill_replay_do_not_double_count():
    adapter = TimeoutAdapter("FILLED", executed_qty=1.0)
    adapter.account = BrokerAccount("IBKR-01", "IBKR", "DEMO")
    lifecycle = OrderLifecycle()
    pending = PendingOrderStore(":memory:")
    from app.pending_orders import PendingOrder
    from app.order_lifecycle import OrderUpdate

    pending.mark(PendingOrder(
        "IBKR", "IBKR-01", "GMAI-IBKR-RACE", "AAPL", "BUY", 1.0
    ))
    lifecycle.apply(OrderUpdate(
        broker="IBKR",
        account_id="IBKR-01",
        client_order_id="GMAI-IBKR-RACE",
        status=OrderStatus.UNKNOWN,
        symbol="AAPL",
        side="BUY",
        original_quantity=1.0,
    ))

    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("IBKR-01", "IBKR", {"USD": 1000.0}, [])
    positions = PositionEngine()
    coordinator = ExecutionCoordinator(
        lifecycle,
        TradingJournal(":memory:"),
        EventBus(),
        positions=positions,
        execution_ledger=ExecutionLedger(":memory:"),
    )
    recovery = BrokerRecovery(
        accounts, state, TradingJournal(":memory:"),
        lifecycle=lifecycle,
        pending_orders=pending,
        execution_coordinator=coordinator,
    )

    live_partial = OrderUpdate(
        broker="IBKR",
        account_id="IBKR-01",
        client_order_id="GMAI-IBKR-RACE",
        status=OrderStatus.PARTIALLY_FILLED,
        symbol="AAPL",
        executed_quantity=0.4,
        average_price=210.0,
        broker_order_id="9004",
        side="BUY",
        original_quantity=1.0,
    )

    await __import__("asyncio").gather(
        recovery.recover_account("IBKR-01"),
        coordinator.broker_update(live_partial),
    )

    position = positions.get("IBKR-01", "AAPL")
    assert position is not None
    assert position.quantity == pytest.approx(1.0)
    assert lifecycle.get("GMAI-IBKR-RACE", "IBKR-01", "IBKR").status is OrderStatus.FILLED
    assert pending.list_account("IBKR-01", "IBKR") == []
