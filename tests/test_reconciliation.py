from app.reconciliation import ReconciliationEngine

def test_reconciliation_accepts_matching_positions():
    result = ReconciliationEngine().compare("A", {"BTC": 1}, [{"asset": "BTC", "quantity": 1.000000001}])
    assert result.ok

def test_reconciliation_detects_mismatch():
    result = ReconciliationEngine().compare("A", {"BTC": 1}, [{"asset": "BTC", "quantity": 0.9}])
    assert not result.ok
    assert "BTC" in result.discrepancies[0]