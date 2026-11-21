from __future__ import annotations

from dataclasses import dataclass

@dataclass
class ExecutionGate:
    """Blocks new orders until broker state is confirmed and risk gates pass."""
    global_enabled: bool = True
    live_trading_enabled: bool = False

    def assert_ready(self, *, account_enabled: bool, state_confirmed: bool,
                     daily_loss_ok: bool, live_enabled: bool) -> None:
        if not self.global_enabled:
            raise RuntimeError("Execution gate is disabled")
        if not account_enabled:
            raise RuntimeError("Account is disabled")
        if not state_confirmed:
            raise RuntimeError("Broker state is not reconciled")
        if not daily_loss_ok:
            raise RuntimeError("Daily loss limit reached")
        if not live_enabled:
            raise RuntimeError("Live execution is not enabled")
