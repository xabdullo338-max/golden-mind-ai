from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .order_models import OrderRequest, OrderSide
from .portfolio import AccountSnapshot


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


class RiskEngine:
    """Pre-trade risk controls shared by PAPER/TESTNET and LIVE gates."""

    def __init__(
        self,
        max_risk_per_trade_pct: float = 0.25,
        max_daily_loss_pct: float = 3.0,
        max_open_positions: int = 3,
        max_notional_pct: float = 100.0,
        max_spread_pct: float = 0.08,
        max_slippage_pct: float = 0.20,
    ):
        if not 0 < max_risk_per_trade_pct <= 100:
            raise ValueError("max_risk_per_trade_pct must be in (0, 100]")
        if not 0 < max_daily_loss_pct <= 100:
            raise ValueError("max_daily_loss_pct must be in (0, 100]")
        if max_open_positions < 1:
            raise ValueError("max_open_positions must be positive")
        if not 0 < max_notional_pct <= 1000:
            raise ValueError("max_notional_pct must be in (0, 1000]")
        if not 0 < max_spread_pct <= 100:
            raise ValueError("max_spread_pct must be in (0, 100]")
        if not 0 < max_slippage_pct <= 100:
            raise ValueError("max_slippage_pct must be in (0, 100]")
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_open_positions = max_open_positions
        self.max_notional_pct = max_notional_pct
        self.max_spread_pct = max_spread_pct
        self.max_slippage_pct = max_slippage_pct

    def check(
        self,
        order: OrderRequest,
        snapshot: AccountSnapshot | None,
        *,
        current_price: float | None = None,
        stop_price: float | None = None,
        spread_pct: float | None = None,
        expected_fill_price: float | None = None,
    ) -> RiskDecision:
        if snapshot is None:
            return RiskDecision(False, "risk snapshot is unavailable")
        if snapshot.equity <= 0:
            return RiskDecision(False, "account equity must be positive")
        if snapshot.daily_loss_pct >= self.max_daily_loss_pct:
            return RiskDecision(False, "daily loss limit reached")
        if snapshot.open_positions >= self.max_open_positions and order.side == OrderSide.BUY:
            return RiskDecision(False, "maximum open positions reached")

        price = expected_fill_price or current_price
        if price is None or price <= 0:
            return RiskDecision(False, "market price is required for risk validation")

        notional = order.quantity * price
        if notional > snapshot.equity * self.max_notional_pct / 100:
            return RiskDecision(False, "maximum position notional exceeded")

        if stop_price is not None:
            if order.side == OrderSide.BUY:
                risk_per_unit = max(0.0, price - stop_price)
            else:
                risk_per_unit = max(0.0, stop_price - price)
            trade_risk = order.quantity * risk_per_unit
            if trade_risk > snapshot.equity * self.max_risk_per_trade_pct / 100:
                return RiskDecision(False, "maximum risk per trade exceeded")

        if spread_pct is not None and spread_pct > self.max_spread_pct:
            return RiskDecision(False, "spread limit exceeded")

        if expected_fill_price is not None and current_price:
            slippage_pct = abs(expected_fill_price - current_price) / current_price * 100
            if slippage_pct > self.max_slippage_pct:
                return RiskDecision(False, "slippage limit exceeded")

        return RiskDecision(True, "risk checks passed")

    def assert_allowed(self, *args, **kwargs) -> None:
        decision = self.check(*args, **kwargs)
        if not decision.allowed:
            raise RuntimeError(decision.reason)
