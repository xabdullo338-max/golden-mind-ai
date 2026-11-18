import pytest

from app.account_manager import AccountManager
from app.binance_execution_bridge import BinanceExecutionBridge
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.event_bus import EventBus
from app.execution_coordinator import ExecutionCoordinator
from app.journal import TradingJournal
from app.order_lifecycle import OrderLifecycle
from app.portfolio_state import PortfolioStateManager
from app.recovery import BrokerRecovery


class FakeBroker(BrokerAdapter):
    def __init__(self, fail=False):
        self.account = BrokerAccount("BINANCE-01", "BINANCE", "PAPER")
        self.fail = fail

    async def get_balance(self):
        return {"USDT": 300.0}

    async def get_positions(self):
        return []

    async def get_open_orders(self, symbol=None):
        if self.fail:
            raise RuntimeError("broker unavailable")
        return []

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status": "PAPER"}

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


@pytest.mark.asyncio
async def test_disconnect_blocks_until_recovery(tmp_path):
    accounts = AccountManager()
    accounts.register(FakeBroker())
    state = PortfolioStateManager()
    journal = TradingJournal(str(tmp_path / "journal.db"))
    recovery = BrokerRecovery(accounts, state, journal)
    coordinator = ExecutionCoordinator(OrderLifecycle(), journal, EventBus())

    bridge = BinanceExecutionBridge(
        "BINANCE-01", coordinator, portfolio_state=state, recovery=recovery
    )

    await recovery.recover_account("BINANCE-01")
    assert state.is_confirmed("BINANCE-01") is True

    bridge.mark_disconnected()
    assert state.is_confirmed("BINANCE-01") is False

    result = await bridge.mark_reconnected_and_recover()
    assert result is True
    assert state.is_confirmed("BINANCE-01") is True


@pytest.mark.asyncio
async def test_failed_recovery_keeps_account_unconfirmed(tmp_path):
    accounts = AccountManager()
    accounts.register(FakeBroker(fail=True))
    state = PortfolioStateManager()
    journal = TradingJournal(str(tmp_path / "journal.db"))
    recovery = BrokerRecovery(accounts, state, journal)
    coordinator = ExecutionCoordinator(OrderLifecycle(), journal, EventBus())

    bridge = BinanceExecutionBridge(
        "BINANCE-01", coordinator, portfolio_state=state, recovery=recovery
    )

    bridge.mark_disconnected()
    result = await bridge.mark_reconnected_and_recover()

    assert result is False
    assert state.is_confirmed("BINANCE-01") is False
