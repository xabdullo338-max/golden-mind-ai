from app.risk import RiskConfig, RiskEngine

def test_risk_engine_approves_normal_trade():
    engine = RiskEngine(RiskConfig(max_risk_per_trade_pct=1.0))
    ok, reason, qty = engine.approve(300, 100, 97, 0, 0)
    assert ok is True
    assert reason == "Risk approved"
    assert round(qty, 2) == 1.0

def test_daily_loss_halts_trading():
    engine = RiskEngine(RiskConfig(max_daily_loss_pct=3.0))
    ok, _, _ = engine.approve(300, 100, 97, 0, -9)
    assert ok is False

def test_position_limit():
    engine = RiskEngine(RiskConfig(max_open_positions=3))
    ok, _, _ = engine.approve(300, 100, 97, 3, 0)
    assert ok is False
