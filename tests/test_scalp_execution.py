import pytest
from datetime import datetime, timezone

from app.account_manager import AccountManager
from app.brokers.base import BrokerAccount
from app.brokers.base import BrokerAdapter
from app.market_data import MarketTick
from app.portfolio import AccountSnapshot
from app.scalping_engine import ScalpingEngine, ScalpingEngineConfig
from app.scalp_execution import ScalpExecutionPipeline

class DummyBroker(BrokerAdapter):
    def __init__(self):
        self.account = BrokerAccount("A", "PAPER", "PAPER")
    async def get_balance(self): return {"USDT": 300.0}
    async def get_positions(self): return []
    async def place_order(self, symbol, side, quantity, order_type="MARKET", **kwargs):
        return {"status":"PAPER","symbol":symbol,"side":side,"quantity":quantity}
    async def cancel_order(self, symbol, order_id): return {"status":"PAPER"}

@pytest.mark.asyncio
async def test_scalp_pipeline_submits():
    accounts = AccountManager()
    accounts.register(DummyBroker())
    snapshots = {"A": AccountSnapshot("A",300,300,0,0,300,0)}
    engine = ScalpingEngine(ScalpingEngineConfig(min_move_pct=0.01))
    pipe = ScalpExecutionPipeline(accounts, snapshots, scalping_engine=engine)
    tick = MarketTick("PAPER","BTCUSDT",100.2,datetime.now(timezone.utc),100.15,100.2)
    result = await pipe.on_tick("A", tick, 100.0, 99.8)
    assert result.submitted is True
    assert result.order is not None
