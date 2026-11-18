from __future__ import annotations

from dataclasses import dataclass

from .portfolio import AccountSnapshot, DailyLossGuard
from .position_sizing import PositionSizing, size_position

@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    sizing: PositionSizing | None = None

class PortfolioRiskEngine:
    """Final pre-order risk decision. It does not place orders."""

    def __init__(self, max_daily_loss_pct: float = 3.0, max_risk_per_trade_pct: float = 1.0):
        self.daily_guard = DailyLossGuard(max_daily_loss_pct)
        self.max_risk_per_trade_pct = max_risk_per_trade_pct

    def evaluate(
        self,
        snapshot: AccountSnapshot,
        entry_price: float,
        stop_price: float,
        requested_risk_pct: float | None = None,
        max_notional: float | None = None,
    ) -> RiskDecision:
        if not self.daily_guard.allowed(snapshot):
            return RiskDecision(False, "daily loss limit reached")
        risk_pct = requested_risk_pct if requested_risk_pct is not None else self.max_risk_per_trade_pct
        if risk_pct <= 0 or risk_pct > self.max_risk_per_trade_pct:
            return RiskDecision(False, "requested risk exceeds account policy")
        try:
            sizing = size_position(
                snapshot.equity, entry_price, stop_price, risk_pct, max_notional
            )
        except ValueError as exc:
            return RiskDecision(False, str(exc))
        if sizing.quantity <= 0 or sizing.notional <= 0:
            return RiskDecision(False, "calculated position is zero")
        return RiskDecision(True, "approved", sizing)
