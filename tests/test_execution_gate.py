import pytest
from app.execution_gate import ExecutionGate

def test_gate_blocks_unconfirmed_state():
    with pytest.raises(RuntimeError, match="not reconciled"):
        ExecutionGate().assert_ready(account_enabled=True, state_confirmed=False, daily_loss_ok=True, live_enabled=True)

def test_gate_blocks_when_live_is_off():
    with pytest.raises(RuntimeError, match="not enabled"):
        ExecutionGate().assert_ready(account_enabled=True, state_confirmed=True, daily_loss_ok=True, live_enabled=False)