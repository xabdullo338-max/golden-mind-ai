import pytest

from app.order_models import OrderRequest, OrderSide
from app.portfolio import AccountSnapshot
from app.risk_engine import RiskEngine


def snapshot(**kwargs):
    values = dict(
        account_id="A", equity=1000.0, cash=1000.0,
        realized_pnl=0.0, unrealized_pnl=0.0,
        daily_start_equity=1000.0, open_positions=0,
    )
    values.update(kwargs)
    return AccountSnapshot(**values)


def order(qty=1.0, side=OrderSide.BUY):
    return OrderRequest("r-1", "BTCUSDT", side, qty)


def test_daily_loss_blocks_new_trade():
    engine = RiskEngine(max_daily_loss_pct=3.0)
    d = engine.check(order(), snapshot(equity=960.0), current_price=100.0)
    assert not d.allowed
    assert "daily loss" in d.reason


def test_position_limit_blocks_new_buy():
    engine = RiskEngine(max_open_positions=3)
    d = engine.check(order(), snapshot(open_positions=3), current_price=100.0)
    assert not d.allowed
    assert "open positions" in d.reason


def test_trade_risk_limit_uses_stop_distance():
    engine = RiskEngine(max_risk_per_trade_pct=1.0)
    d = engine.check(order(qty=1.0), snapshot(), current_price=100.0, stop_price=80.0)
    assert not d.allowed
    assert "risk per trade" in d.reason


def test_notional_limit_blocks_oversized_order():
    engine = RiskEngine(max_notional_pct=50.0)
    d = engine.check(order(qty=6.0), snapshot(), current_price=100.0)
    assert not d.allowed
    assert "notional" in d.reason


def test_spread_and_slippage_guards():
    engine = RiskEngine(max_spread_pct=0.08, max_slippage_pct=0.2)
    assert not engine.check(order(), snapshot(), current_price=100.0, spread_pct=0.09).allowed
    assert not engine.check(order(), snapshot(), current_price=100.0, expected_fill_price=100.3).allowed


def test_valid_trade_passes():
    engine = RiskEngine(max_risk_per_trade_pct=1.0, max_notional_pct=50.0)
    d = engine.check(order(qty=0.25), snapshot(), current_price=100.0, stop_price=96.0)
    assert d.allowed
