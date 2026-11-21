from datetime import date

import pytest

from app.daily_risk_state import DailyRiskStateStore
from app.portfolio_state import PortfolioStateManager
from app.position_engine import PositionEngine
from app.risk_snapshot import RiskSnapshotProvider


def test_snapshot_uses_position_pnl(tmp_path):
    state = PortfolioStateManager()
    state.reconcile(
        "A", "BINANCE",
        {"USDT": 700.0, "BTC": 0.01},
        [{"asset": "BTC", "quantity": 0.01}],
    )
    positions = PositionEngine()
    positions.hydrate("A", "BTCUSDT", 0.01, 30000.0, realized_pnl=12.0)

    provider = RiskSnapshotProvider(
        daily_risk_store=DailyRiskStateStore(str(tmp_path / "risk.db")),
        positions=positions,
    )
    snap = provider.build(state.get("A"), prices={"BTCUSDT": 32000.0})
    assert snap is not None
    assert snap.realized_pnl == pytest.approx(12.0)
    assert snap.unrealized_pnl == pytest.approx(20.0)


def test_snapshot_does_not_fabricate_position_mark(tmp_path):
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 700.0}, [])
    positions = PositionEngine()
    positions.hydrate("A", "BTCUSDT", 0.01, 30000.0)

    provider = RiskSnapshotProvider(
        daily_risk_store=DailyRiskStateStore(str(tmp_path / "risk.db")),
        positions=positions,
    )
    assert provider.build(state.get("A"), prices={}) is None
