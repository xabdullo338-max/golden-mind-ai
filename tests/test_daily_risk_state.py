from datetime import date, timedelta

import pytest

from app.daily_risk_state import DailyRiskStateStore
from app.risk_snapshot import RiskSnapshotProvider
from app.portfolio_state import PortfolioStateManager


def test_daily_risk_state_persists_across_restart(tmp_path):
    path = tmp_path / "risk.db"
    store = DailyRiskStateStore(str(path))
    first = store.establish_if_missing("A", date(2026, 11, 21), 1000.0)
    assert first.start_equity == 1000.0

    restarted = DailyRiskStateStore(str(path))
    same_day = restarted.establish_if_missing("A", date(2026, 11, 21), 900.0)
    assert same_day.start_equity == 1000.0


def test_daily_risk_state_rolls_to_new_utc_day(tmp_path):
    store = DailyRiskStateStore(str(tmp_path / "risk.db"))
    store.establish_if_missing("A", date(2026, 11, 21), 1000.0)
    next_day = store.establish_if_missing("A", date(2026, 11, 22), 900.0)
    assert next_day.start_equity == 900.0


def test_snapshot_requires_explicit_baseline_without_store():
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    provider = RiskSnapshotProvider()
    assert provider.build(state.get("A"), prices={}) is None


def test_snapshot_uses_durable_baseline(tmp_path):
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 1000.0}, [])
    provider = RiskSnapshotProvider(
        daily_risk_store=DailyRiskStateStore(str(tmp_path / "risk.db"))
    )
    snapshot = provider.build(state.get("A"), prices={})
    assert snapshot is not None
    assert snapshot.daily_start_equity == pytest.approx(1000.0)

    state.reconcile("A", "BINANCE", {"USDT": 960.0}, [])
    snapshot = provider.build(state.get("A"), prices={})
    assert snapshot is not None
    assert snapshot.daily_start_equity == pytest.approx(1000.0)
    assert snapshot.daily_loss_pct == pytest.approx(4.0)
