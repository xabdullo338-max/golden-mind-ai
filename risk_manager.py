from dataclasses import dataclass


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 1.0
    max_position_pct: float = 25.0
    daily_loss_limit_pct: float = 3.0


class RiskManager:
    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    def validate(self, balance: float, quantity: float, entry_price: float):
        if balance <= 0:
            return False, "Invalid balance"
        if quantity <= 0 or entry_price <= 0:
            return False, "Invalid order size"

        notional = quantity * entry_price
        max_notional = balance * self.config.max_position_pct / 100

        if notional > max_notional:
            return False, "Position exceeds max position limit"

        return True, "OK"
