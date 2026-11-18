from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class HealthReport:
    ok: bool
    checks: dict[str, bool]
    details: dict[str, Any]

class SystemHealth:
    def __init__(self, accounts, kill_switch):
        self.accounts = accounts
        self.kill_switch = kill_switch

    def check(self) -> HealthReport:
        checks = {
            "accounts_registered": bool(self.accounts.accounts),
            "kill_switch_resumed": not self.kill_switch.global_enabled,
        }
        return HealthReport(
            ok=all(checks.values()),
            checks=checks,
            details={"account_count": len(self.accounts.accounts)},
        )
