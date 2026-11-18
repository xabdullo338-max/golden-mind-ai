from app.market_data import MarketTick
from app.portfolio import AccountSnapshot
from app.trade_planner import TradePlanner

def snapshot():
    return AccountSnapshot("A", 300, 300, 0, 0, 300, 0)

def test_planner_creates_risk_approved_plan():
    tick = MarketTick("BINANCE", "BTCUSDT", 100, __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    plan = TradePlanner().plan("A", tick, 101, 100, snapshot(), 95)
    assert plan is not None
    assert plan.side == "BUY"
    assert round(plan.quantity, 4) == 0.6
    assert plan.risk_amount == 3

def test_planner_blocks_daily_loss():
    s = AccountSnapshot("A", 290, 290, 0, 0, 300, 0)
    tick = MarketTick("BINANCE", "BTCUSDT", 100, __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    assert TradePlanner().plan("A", tick, 101, 100, s, 95) is None
