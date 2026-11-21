import pytest

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.event_bus import EventBus
from app.execution_coordinator import ExecutionCoordinator
from app.execution_ledger import ExecutionLedger
from app.journal import TradingJournal
from app.order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate
from app.portfolio_state import PortfolioStateManager
from app.position_engine import PositionEngine
from app.recovery import BrokerRecovery


class RestartScenarioAdapter(BrokerAdapter):
    def __init__(self):
        self.account = BrokerAccount("A", "BINANCE", "TESTNET")
        self.btc = 0.0
        self.trades = []
        self.next_id = 1

    async def get_balance(self):
        return {"USDT": 1000.0 - self.btc * 100.0, "BTC": self.btc}

    async def get_positions(self):
        return [{"asset": "BTC", "quantity": self.btc}] if self.btc > 0 else []

    async def get_open_orders(self, symbol=None):
        return []

    async def get_trade_history(self, symbol, limit=1000):
        return list(self.trades)

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        side = side.upper()
        price = 100.0 if side == "BUY" else 110.0
        if side == "BUY":
            self.btc += quantity
        else:
            self.btc -= quantity
        trade = {
            "id": self.next_id,
            "time": self.next_id,
            "symbol": symbol,
            "isBuyer": side == "BUY",
            "qty": str(quantity),
            "price": str(price),
            "commission": "0",
            "commissionAsset": "USDT",
        }
        self.next_id += 1
        self.trades.append(trade)
        return {
            "status": "FILLED",
            "symbol": symbol,
            "side": side,
            "executedQty": quantity,
            "orderId": str(self.next_id),
            "clientOrderId": kwargs.get("client_order_id", ""),
        }

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


def make_coordinator(ledger_path):
    return ExecutionCoordinator(
        lifecycle=OrderLifecycle(),
        journal=TradingJournal(":memory:"),
        event_bus=EventBus(),
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(ledger_path),
    )


@pytest.mark.asyncio
async def test_partial_fill_disconnect_restart_recover_then_sell_without_double_count(tmp_path):
    adapter = RestartScenarioAdapter()
    accounts = AccountManager()
    accounts.register(adapter)

    state = PortfolioStateManager()

    # Process 1: receive a 0.4 BTC partial fill.
    coordinator1 = make_coordinator(str(tmp_path / "execution.db"))
    await coordinator1.submitted("A", "BINANCE", "buy-1", "BTCUSDT", "BUY", 1.0)
    await coordinator1.broker_update(
        OrderUpdate(
            broker="BINANCE", account_id="A", client_order_id="buy-1",
            status=OrderStatus.PARTIALLY_FILLED, symbol="BTCUSDT",
            executed_quantity=0.4, average_price=100.0, side="BUY",
            last_fill_quantity=0.4, last_fill_price=100.0,
        )
    )
    adapter.btc = 0.4
    adapter.trades = [{
        "id": 1, "time": 1, "symbol": "BTCUSDT", "isBuyer": True,
        "qty": "0.4", "price": "100", "commission": "0",
        "commissionAsset": "USDT",
    }]

    assert coordinator1.positions.get("A", "BTCUSDT").quantity == pytest.approx(0.4)

    # Disconnect/restart: broker becomes authoritative and the new process
    # rebuilds the same 0.4 BTC position from trade history.
    state.mark_unconfirmed("A", "BINANCE")
    coordinator2 = make_coordinator(str(tmp_path / "execution.db"))
    recovery = BrokerRecovery(accounts, state, TradingJournal(":memory:"), positions=coordinator2.positions)
    recovered = await recovery.recover_account("A")

    assert recovered.confirmed is True
    recovered_position = coordinator2.positions.get("A", "BTCUSDT")
    assert recovered_position.quantity == pytest.approx(0.4)
    assert recovered_position.average_entry == pytest.approx(100.0)

    # A repeated broker execution event for the original cumulative 0.4 must
    # produce zero new execution delta after restart.
    repeated = OrderUpdate(
        broker="BINANCE", account_id="A", client_order_id="buy-1",
        status=OrderStatus.PARTIALLY_FILLED, symbol="BTCUSDT",
        executed_quantity=0.4, average_price=100.0, side="BUY",
        last_fill_quantity=0.4, last_fill_price=100.0,
    )
    await coordinator2.broker_update(repeated)
    assert coordinator2.positions.get("A", "BTCUSDT").quantity == pytest.approx(0.4)

    # Sell the recovered position and apply its broker fill once.
    adapter.btc = 0.0
    adapter.trades.append({
        "id": 2, "time": 2, "symbol": "BTCUSDT", "isBuyer": False,
        "qty": "0.4", "price": "110", "commission": "0",
        "commissionAsset": "USDT",
    })
    await coordinator2.submitted("A", "BINANCE", "sell-1", "BTCUSDT", "SELL", 0.4)
    await coordinator2.broker_update(
        OrderUpdate(
            broker="BINANCE", account_id="A", client_order_id="sell-1",
            status=OrderStatus.FILLED, symbol="BTCUSDT",
            executed_quantity=0.4, average_price=110.0, side="SELL",
            last_fill_quantity=0.4, last_fill_price=110.0,
        )
    )

    assert coordinator2.positions.snapshot("A") == []
