import pytest
from datetime import datetime, timezone

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount, BrokerAdapter
from app.execution_gate import ExecutionGate
from app.market_data import MarketTick
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter
from app.portfolio_state import PortfolioStateManager
from app.risk_engine import RiskEngine
from app.risk_snapshot import RiskSnapshotProvider


class RiskAdapter(BrokerAdapter):
    def __init__(self):
        self.account = BrokerAccount("A", "BINANCE", "TESTNET")
        self.orders = 0

    async def get_balance(self):
        return {"USDT": 1000.0, "BTC": 0.01}

    async def get_positions(self):
        return [{"asset": "BTC", "quantity": 0.01}]

    async def get_market_tick(self, symbol):
        prices = {"BTCUSDT": 30000.0, "ETHUSDT": 2000.0}
        return MarketTick("BINANCE", symbol, prices[symbol], datetime.now(timezone.utc))

    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        self.orders += 1
        return {"status": "FILLED", "symbol": symbol, "executedQty": quantity}

    async def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}


@pytest.mark.asyncio
async def test_router_blocks_when_market_data_is_stale():
    manager = AccountManager()
    adapter = RiskAdapter()
    manager.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    router = OrderRouter(
        manager,
        execution_gate=ExecutionGate(),
        portfolio_state=state,
        risk_engine=RiskEngine(max_market_data_age_seconds=2.0),
        risk_snapshot_provider=RiskSnapshotProvider(),
        market_tick_provider=lambda account_id, symbol: _stale_tick(symbol),
    )
    with pytest.raises(RuntimeError, match="stale"):
        await router.route("A", OrderRequest("risk-1", "BTCUSDT", OrderSide.BUY, 0.001))
    assert adapter.orders == 0


async def _stale_tick(symbol):
    from datetime import timedelta
    return MarketTick(
        "BINANCE", symbol, 30000.0,
        datetime.now(timezone.utc) - timedelta(seconds=3),
    )


@pytest.mark.asyncio
async def test_router_uses_broker_snapshot_and_exposure():
    manager = AccountManager()
    adapter = RiskAdapter()
    manager.register(adapter)
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 700.0, "BTC": 0.01}, [{"asset": "BTC", "quantity": 0.01}])
    router = OrderRouter(
        manager,
        execution_gate=ExecutionGate(),
        portfolio_state=state,
        risk_engine=RiskEngine(max_total_exposure_pct=100.0, max_symbol_exposure_pct=50.0),
        risk_snapshot_provider=RiskSnapshotProvider(),
        market_tick_provider=adapter.get_market_tick,
    )
    with pytest.raises(RuntimeError, match="symbol exposure"):
        await router.route("A", OrderRequest("risk-2", "BTCUSDT", OrderSide.BUY, 0.001))
    assert adapter.orders == 0
