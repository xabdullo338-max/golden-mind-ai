import pytest

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.idempotency import OrderIdempotencyGuard
from app.order_lifecycle import OrderLifecycle, OrderStatus
from app.order_models import OrderRequest, OrderSide, OrderType
from app.order_router import OrderRouter
from app.portfolio_state import PortfolioStateManager
from app.recovery import BrokerRecovery
from app.journal import TradingJournal


class OpenOrderAdapter(BrokerAdapter):
    def __init__(self):
        self.account = BrokerAccount("A", "BINANCE", "TESTNET")
        self.open_orders = []
        self.submissions = 0

    async def get_balance(self):
        return {"USDT": 1000.0}

    async def get_positions(self):
        return []

    async def get_open_orders(self, symbol=None):
        orders = list(self.open_orders)
        if symbol:
            orders = [o for o in orders if o["symbol"] == symbol]
        return orders

    async def get_trade_history(self, symbol, limit=1000):
        return []

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        self.submissions += 1
        order = {
            "status": "NEW",
            "symbol": symbol,
            "side": side,
            "origQty": str(quantity),
            "executedQty": "0",
            "clientOrderId": kwargs["client_order_id"],
            "orderId": "9001",
        }
        self.open_orders.append(order)
        return order

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


def build_router(adapter, lifecycle):
    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    return OrderRouter(
        accounts,
        idempotency=OrderIdempotencyGuard(),
        lifecycle=lifecycle,
        portfolio_state=state,
    )


@pytest.mark.asyncio
async def test_restart_recovers_new_order_and_blocks_duplicate_submission():
    adapter = OpenOrderAdapter()
    lifecycle1 = OrderLifecycle()
    state = PortfolioStateManager()
    accounts = AccountManager()
    accounts.register(adapter)
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    recovery1 = BrokerRecovery(accounts, state, TradingJournal(":memory:"), lifecycle=lifecycle1)

    adapter.open_orders = [{
        "status": "NEW",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "origQty": "0.5",
        "executedQty": "0",
        "price": "100",
        "clientOrderId": "buy-1",
        "orderId": "9001",
    }]
    result = await recovery1.recover_account("A")
    assert result.confirmed is True
    recovered = lifecycle1.get("buy-1", "A", "BINANCE")
    assert recovered is not None
    assert recovered.status == OrderStatus.NEW
    assert recovered.original_quantity == pytest.approx(0.5)

    # Simulate process restart: the old in-memory idempotency state is gone,
    # but broker truth is hydrated into the new lifecycle before routing.
    lifecycle2 = OrderLifecycle()
    recovery2 = BrokerRecovery(accounts, state, TradingJournal(":memory:"), lifecycle=lifecycle2)
    await recovery2.recover_account("A")

    router = build_router(adapter, lifecycle2)
    with pytest.raises(RuntimeError, match="duplicate client order id"):
        await router.route("A", OrderRequest(
            client_order_id="buy-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.5,
            order_type=OrderType.LIMIT,
            limit_price=100.0,
        ))
    assert adapter.submissions == 0


@pytest.mark.asyncio
async def test_partial_open_order_recovers_remaining_quantity():
    adapter = OpenOrderAdapter()
    lifecycle = OrderLifecycle()
    accounts = AccountManager()
    accounts.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])

    adapter.open_orders = [{
        "status": "PARTIALLY_FILLED",
        "symbol": "ETHUSDT",
        "side": "BUY",
        "origQty": "2.0",
        "executedQty": "0.75",
        "price": "2000",
        "clientOrderId": "eth-1",
        "orderId": "9002",
    }]

    recovery = BrokerRecovery(accounts, state, TradingJournal(":memory:"), lifecycle=lifecycle)
    result = await recovery.recover_account("A")
    assert result.confirmed is True

    order = lifecycle.get("eth-1", "A", "BINANCE")
    assert order is not None
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.original_quantity == pytest.approx(2.0)
    assert order.executed_quantity == pytest.approx(0.75)
    assert order.original_quantity - order.executed_quantity == pytest.approx(1.25)
