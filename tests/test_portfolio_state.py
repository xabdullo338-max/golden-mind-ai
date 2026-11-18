from app.portfolio_state import PortfolioStateManager

def test_reconnect_requires_reconciliation():
    m = PortfolioStateManager()
    m.mark_unconfirmed("A", "IBKR")
    assert not m.is_confirmed("A")
    state = m.reconcile("A", "IBKR", [{"asset":"AAPL", "quantity":2}], [], [])
    assert state.confirmed
    assert state.positions["AAPL"] == 2