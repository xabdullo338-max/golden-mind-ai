import pytest

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.execution_coordinator import ExecutionCoordinator
from app.event_bus import EventBus
from app.execution_ledger import ExecutionLedger
from app.journal import TradingJournal
from app.order_lifecycle import OrderLifecycle
from app.portfolio_state import PortfolioStateManager
from app.position_engine import PositionEngine
from app.recovery import BrokerRecovery


class PositionRecoveryAdapter(BrokerAdapter):
    def __init__(self, account_id="A"):
        self.account = BrokerAccount(account_id, "TEST", "TESTNET")
        self.trades = [
            {"id": 1, "time": 1, "symbol": "BTCUSDT", "isBuyer": True,
             "qty": "0.4", "price": "100", "commission": "0", "commissionAsset": "USDT"},
            {"id": 2, "time": 2, "symbol": "BTCUSDT", "isBuyer": True,
             "qty": "0.6", "price": "110", "commission": "0", "commissionAsset": "USDT"},
        ]

    async def get_balance(self):
        return {"USDT": 890.0, "BTC": 1.0}

    async def get_positions(self):
        return [{"asset": "BTC", "quantity": 1.0}]

    async def get_open_orders(self, symbol=None):
        return []

    async def get_trade_history(self, symbol, limit=1000):
        return [t for t in self.trades if t["symbol"] == symbol]

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status": "FILLED", "symbol": symbol, "side": side, "executedQty": quantity}

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


@pytest.mark.asyncio
async def test_recovery_reconstructs_weighted_average_entry():
    accounts = AccountManager()
    adapter = PositionRecoveryAdapter()
    accounts.register(adapter)

    state = PortfolioStateManager()
    journal = TradingJournal(":memory:")
    positions = PositionEngine()
    recovery = BrokerRecovery(accounts, state, journal, positions=positions)

    result = await recovery.recover_account("A")

    assert result.confirmed is True
    recovered = positions.get("A", "BTCUSDT")
    assert recovered.quantity == pytest.approx(1.0)
    assert recovered.average_entry == pytest.approx(106.0)


@pytest.mark.asyncio
async def test_recovery_does_not_fabricate_entry_when_history_is_incomplete():
    accounts = AccountManager()
    adapter = PositionRecoveryAdapter()
    adapter.trades = adapter.trades[:1]
    accounts.register(adapter)

    state = PortfolioStateManager()
    journal = TradingJournal(":memory:")
    positions = PositionEngine()
    recovery = BrokerRecovery(accounts, state, journal, positions=positions)

    result = await recovery.recover_account("A")

    # Position history is insufficient to prove the broker quantity.
    # Recovery must fail closed instead of inventing an entry price.
    assert result.confirmed is False
    assert "position history is incomplete" in result.reason
    assert state.is_confirmed("A") is False
    assert positions.snapshot("A") == []


@pytest.mark.asyncio
async def test_recovery_can_replace_stale_local_position_when_history_matches():
    accounts = AccountManager()
    adapter = PositionRecoveryAdapter()
    accounts.register(adapter)

    state = PortfolioStateManager()
    journal = TradingJournal(":memory:")
    positions = PositionEngine()
    positions.hydrate("A", "BTCUSDT", 0.5, 50.0)
    recovery = BrokerRecovery(accounts, state, journal, positions=positions)

    await recovery.recover_account("A")

    recovered = positions.get("A", "BTCUSDT")
    assert recovered.quantity == pytest.approx(1.0)
    assert recovered.average_entry == pytest.approx(106.0)
