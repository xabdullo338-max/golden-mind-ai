from app.portfolio_state import PortfolioStateManager
from app.risk_snapshot import RiskSnapshotProvider


def test_risk_snapshot_values_reconciled_assets():
    state = PortfolioStateManager()
    state.reconcile(
        "A", "BINANCE",
        {"USDT": 700.0, "BTC": 0.01},
        [{"asset": "BTC", "quantity": 0.01}],
    )
    snap = RiskSnapshotProvider(daily_start_equity={"A": 1000.0}).build(state.get("A"), prices={"BTCUSDT": 30000.0})
    assert snap is not None
    assert snap.equity == 1000.0
    assert snap.cash == 700.0
    assert snap.open_positions == 1


def test_risk_snapshot_refuses_unconfirmed_state():
    state = PortfolioStateManager()
    state.mark_unconfirmed("A", "BINANCE")
    assert RiskSnapshotProvider().build(state.get("A"), prices={"BTCUSDT": 30000.0}) is None


def test_risk_snapshot_refuses_missing_price():
    state = PortfolioStateManager()
    state.reconcile("A", "BINANCE", {"USDT": 700.0, "BTC": 0.01}, [])
    assert RiskSnapshotProvider().build(state.get("A"), prices={}) is None
