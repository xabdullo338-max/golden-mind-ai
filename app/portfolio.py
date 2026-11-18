from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    equity: float
    cash: float
    realized_pnl: float
    unrealized_pnl: float
    daily_start_equity: float
    open_positions: int

    @property
    daily_pnl(self) -> float:
        return self.equity - self.daily_start_equity

    @property
    daily_loss_pct(self) -> float:
        if self.daily_start_equity <= 0:
            return 100.0
        return max(0.0, -self.daily_pnl / self.daily_start_equity * 100)

class DailyLossGuard:
    def __init__(self, max_daily_loss_pct: float = 3.0):
        if max_daily_loss_pct <= 0:
            raise ValueError("max_daily_loss_pct must be positive")
        self.max_daily_loss_pct = max_daily_loss_pct

    def allowed(self, snapshot: AccountSnapshot) -> bool:
        return snapshot.daily_loss_pct < self.max_daily_loss_pct

    def assert_allowed(self, snapshot: AccountSnapshot) -> None:
        if not self.allowed(snapshot):
            raise RuntimeError(
                f"Daily loss limit reached for {snapshot.account_id}: "
                f"{snapshot.daily_loss_pct:.2f}% >= {self.max_daily_loss_pct:.2f}%"
            )

def utc_date() -> date:
    return datetime.now(timezone.utc).date()
