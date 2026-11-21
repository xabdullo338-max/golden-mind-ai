import pytest

from app.account_manager import AccountManager
from app.binance_execution_bridge import BinanceExecutionBridge
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.execution_coordinator import ExecutionCoordinator
from app.event_bus import EventBus
from app.execution_ledger import ExecutionLedger
from app.journal import TradingJournal
from app.order_lifecycle import OrderLifecycle
from app.portfolio_state import PortfolioStateManager
from app.position_engine import PositionEngine
from app.recovery import BrokerRecovery


class RecoveryAdapter(BrokerAdapter):
    def __init__(self, account_id="A"):
        self.account = BrokerAccount(account_id, "TEST", "TESTNET")
        self.fail_recovery = False

    async def get_balance(self):
        if self.fail_recovery:
            raise RuntimeError("broker unavailable")
        return {"USDT": 997.0}

    async def get_positions(self):
        if self.fail_recovery:
            raise RuntimeError("broker unavailable")
        return []

    async def get_open_orders(self):
        if self.fail_recovery:
            raise RuntimeError("broker unavailable")
        return []

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status": "FILLED", "symbol": symbol, "side": side, "executedQty": quantity}

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


class DummyJournal:
    def record(self, *args, **kwargs):
        return None


def build_bridge():
    accounts = AccountManager()
    adapter = RecoveryAdapter()
    accounts.register(adapter)

    state = PortfolioStateManager()
    state.reconcile("A", "TEST", {"USDT": 1000.0}, [])

    recovery = BrokerRecovery(accounts, state, DummyJournal())
    coordinator = ExecutionCoordinator(
        OrderLifecycle(),
        TradingJournal(":memory:"),
        EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    bridge = BinanceExecutionBridge(
        "A",
        coordinator,
        portfolio_state=state,
        recovery=recovery,
    )
    return bridge, adapter, state


@pytest.mark.asyncio
async def test_disconnect_blocks_until_successful_recovery():
    bridge, adapter, state = build_bridge()

    bridge.mark_disconnected()
    assert not state.is_confirmed("A")

    recovered = await bridge.mark_reconnected_and_recover()

    assert recovered is True
    assert state.is_confirmed("A")
    assert state.get("A").balances == {"USDT": 997.0}


@pytest.mark.asyncio
async def test_failed_recovery_keeps_state_unconfirmed():
    bridge, adapter, state = build_bridge()

    bridge.mark_disconnected()
    adapter.fail_recovery = True

    recovered = await bridge.mark_reconnected_and_recover()

    assert recovered is False
    assert not state.is_confirmed("A")


@pytest.mark.asyncio
async def test_recovery_requires_broker_truth_not_stale_local_state():
    bridge, adapter, state = build_bridge()

    state.mark_unconfirmed("A", "TEST")
    adapter.fail_recovery = True

    failed = await bridge.mark_reconnected_and_recover()
    assert failed is False
    assert not state.is_confirmed("A")

    adapter.fail_recovery = False
    successful = await bridge.mark_reconnected_and_recover()
    assert successful is True
    assert state.is_confirmed("A")
from app.recovery import RecoveryPhase


def test_recovery_phase_starts_idle():
    recovery = make_recovery()
    assert recovery.phase("A") is RecoveryPhase.IDLE


@pytest.mark.asyncio
async def test_recovery_failure_enters_failed_phase():
    recovery = make_recovery(failing=True)
    result = await recovery.recover_account("A")
    assert result.confirmed is False
    assert recovery.phase("A") is RecoveryPhase.FAILED


@pytest.mark.asyncio
async def test_successful_recovery_enters_confirmed_phase():
    recovery = make_recovery()
    result = await recovery.recover_account("A")
    assert result.confirmed is True
    assert recovery.phase("A") is RecoveryPhase.CONFIRMED
