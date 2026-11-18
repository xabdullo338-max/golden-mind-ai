import pytest
from app.portfolio import AccountSnapshot, DailyLossGuard

def test_daily_loss_guard_allows_normal_day():
    s = AccountSnapshot("A", 990, 900, 0, -10, 1000, 1)
    assert DailyLossGuard(3).allowed(s)

def test_daily_loss_guard_blocks_limit():
    s = AccountSnapshot("A", 969, 900, -20, -11, 1000, 2)
    with pytest.raises(RuntimeError):
        DailyLossGuard(3).assert_allowed(s)