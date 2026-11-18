import pytest

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.journal import TradingJournal
from app.portfolio_state import PortfolioStateManager
from app.recovery import BrokerRecovery
from app.reconnect_policy import ReconnectPolicy


class FakeBroker(BrokerAdapter):
    def __init__(self, fail_orders: bool = False):
        self.account = BrokerAccount("A", "TEST", "PAPER")
        self.fail_orders = fail_orders

    async def get_balance(self):
        return {"USD": 1000}

    async def get_positions(self):
        return [{"asset": "BTC", "quantity": 0.25}]

    async def get_open_orders(self, symbol=None):
        if self.fail_orders:
            raise RuntimeError("broker unavailable")
        return [{"symbol": "BTCUSDT", "status": "NEW"}]

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status": "PAPER"}

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


@pytest.mark.asyncio
async def test_recovery_reconciles_and_confirms_state(tmp_path):
    accounts = AccountManager()
    accounts.register(FakeBroker())
    state = PortfolioStateManager()
    journal = TradingJournal(str(tmp_path / "journal.db"))

    result = await BrokerRecovery(accounts, state, journal).recover_account("A")

    assert result.confirmed is True
    assert state.is_confirmed("A") is True
    recovered = state.get("A")
    assert recovered is not None
    assert recovered.balances == {"USD": 1000.0}
    assert recovered.positions == {"BTC": 0.25}
    assert recovered.open_orders == [{"symbol": "BTCUSDT", "status": "NEW"}]


@pytest.mark.asyncio
async def test_recovery_marks_state_unconfirmed_on_open_order_failure(tmp_path):
    accounts = AccountManager()
    accounts.register(FakeBroker(fail_orders=True))
    state = PortfolioStateManager()
    journal = TradingJournal(str(tmp_path / "journal.db"))

    result = await BrokerRecovery(accounts, state, journal).recover_account("A")

    assert result.confirmed is False
    assert state.is_confirmed("A") is False


def test_backoff_is_bounded():
    policy = ReconnectPolicy(max_attempts=10, base_delay_seconds=1, max_delay_seconds=8)
    assert policy.delay(1) == 1
    assert policy.delay(4) == 8
    assert policy.delay(10) == 8
