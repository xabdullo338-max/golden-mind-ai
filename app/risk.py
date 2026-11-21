from dataclasses import dataclass

from .portfolio import AccountSnapshot, DailyLossGuard

@dataclass(frozen=True)
class RiskConfig:
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_open_positions: int = 3

class RiskEngine:
    def __init__(self, config: RiskConfig):
        self.config = config

    def approve(self, balance: float, entry: float, stop: float, open_positions: int, daily_pnl: float) -> tuple[bool, str, float]:
        if balance <= 0 or entry <= 0 or stop <= 0:
            return False, "Invalid balance/price/stop", 0.0
        if open_positions >= self.config.max_open_positions:
            return False, "Maximum open positions reached", 0.0
        daily_limit = balance * self.config.max_daily_loss_pct / 100
        if daily_pnl <= -daily_limit:
            return False, "Daily loss limit reached", 0.0
        risk_amount = balance * self.config.max_risk_per_trade_pct / 100
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return False, "Stop-loss distance must be positive", 0.0
        quantity = risk_amount / stop_distance
        return True, "Risk approved", quantity
