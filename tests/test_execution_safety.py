from app.execution_ledger import ExecutionLedger
from app.idempotency import OrderIdempotencyGuard

def test_execution_delta_uses_cumulative_quantity():
    ledger = ExecutionLedger()
    assert ledger.delta("1", 2.0) == 2.0
    assert ledger.delta("1", 2.0) == 0.0
    assert ledger.delta("1", 3.5) == 1.5

def test_idempotency_guard_rejects_duplicate():
    guard = OrderIdempotencyGuard()
    assert guard.check_and_mark("gmai-1").allowed
    assert not guard.check_and_mark("gmai-1").allowed
