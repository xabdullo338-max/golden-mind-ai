import pytest
from app.position_sizing import size_position

def test_position_size_respects_risk():
    s = size_position(1000, 100, 95, 1)
    assert s.risk_amount == 10
    assert s.quantity == 2

def test_position_size_respects_max_notional():
    s = size_position(1000, 100, 50, 2, max_notional=100)
    assert s.notional == 100
    assert s.quantity == 1

def test_position_size_rejects_same_stop():
    with pytest.raises(ValueError):
        size_position(1000, 100, 100, 1)