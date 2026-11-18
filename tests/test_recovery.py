from app.recovery import BrokerRecovery, RecoveryResult
from app.reconnect_policy import ReconnectPolicy

def test_backoff_is_bounded():
    policy = ReconnectPolicy(max_attempts=10, base_delay_seconds=1, max_delay_seconds=8)
    assert policy.delay(1) == 1
    assert policy.delay(4) == 8
    assert policy.delay(10) == 8
