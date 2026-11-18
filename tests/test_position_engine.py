import pytest
from app.position_engine import PositionEngine

def test_buy_updates_average_entry():
    e = PositionEngine()
    p = e.apply_fill("A", "BTCUSDT", "BUY", 1, 100)
    e.apply_fill("A", "BTCUSDT", "BUY", 1, 120)
    assert p.quantity == 2
    assert p.average_entry == 110

def test_partial_sell_realizes_pnl():
    e = PositionEngine()
    e.apply_fill("A", "BTCUSDT", "BUY", 2, 100)
    p = e.apply_fill("A", "BTCUSDT", "SELL", 0.5, 120, commission=1)
    assert p.quantity == 1.5
    assert p.realized_pnl == 9

def test_oversell_is_rejected():
    e = PositionEngine()
    e.apply_fill("A", "BTCUSDT", "BUY", 1, 100)
    with pytest.raises(RuntimeError):
        e.apply_fill("A", "BTCUSDT", "SELL", 2, 120)
