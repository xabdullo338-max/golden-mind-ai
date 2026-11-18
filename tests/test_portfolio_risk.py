from app.portfolio import AccountSnapshot
from app.portfolio_risk import PortfolioRiskEngine

def snap(equity=300, daily_start=300):
    return AccountSnapshot("A", equity, equity, 0, 0, daily_start, 0)

def test_risk_engine_approves_valid_trade():
    decision = PortfolioRiskEngine().evaluate(snap(), 100, 95)
    assert decision.approved
    assert decision.sizing is not None
    assert round(decision.sizing.risk_amount, 2) == 3.0

def test_risk_engine_blocks_daily_loss():
    decision = PortfolioRiskEngine().evaluate(snap(290, 300), 100, 95)
    assert not decision.approved
    assert "daily loss" in decision.reason

def test_risk_engine_blocks_excessive_risk():
    decision = PortfolioRiskEngine().evaluate(snap(), 100, 95, requested_risk_pct=2)
    assert not decision.approved
