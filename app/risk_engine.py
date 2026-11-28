from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

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
        max_total_exposure_pct: float = 100.0,
        max_symbol_exposure_pct: float = 100.0,
        cooldown_seconds: float = 0.0,
        max_consecutive_losses: int = 0,
        max_market_data_age_seconds: float = 2.0,
        max_order_notional_usdt: float | None = None,
        clock: Any = time.monotonic,
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
        if not 0 < max_total_exposure_pct <= 1000:
            raise ValueError("max_total_exposure_pct must be in (0, 1000]")
        if not 0 < max_symbol_exposure_pct <= 1000:
            raise ValueError("max_symbol_exposure_pct must be in (0, 1000]")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be non-negative")
        if max_consecutive_losses < 0:
            raise ValueError("max_consecutive_losses must be non-negative")
        if max_market_data_age_seconds <= 0:
            raise ValueError("max_market_data_age_seconds must be positive")
        if max_order_notional_usdt is not None and max_order_notional_usdt <= 0:
            raise ValueError("max_order_notional_usdt must be positive")
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_open_positions = max_open_positions
        self.max_notional_pct = max_notional_pct
        self.max_spread_pct = max_spread_pct
        self.max_slippage_pct = max_slippage_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.max_symbol_exposure_pct = max_symbol_exposure_pct
        self.cooldown_seconds = cooldown_seconds
        self.max_consecutive_losses = max_consecutive_losses
        self.max_market_data_age_seconds = max_market_data_age_seconds
        self.max_order_notional_usdt = max_order_notional_usdt
        self._clock = clock
        self._last_order_at: dict[str, float] = {}
        self._consecutive_losses: dict[str, int] = {}

    def record_order_accepted(self, account_id: str) -> None:
        """Start the cooldown only after the broker accepted the order."""
        if self.cooldown_seconds:
            self._last_order_at[account_id] = self._clock()

    def record_trade_result(self, account_id: str, pnl: float) -> None:
        if pnl < 0:
            self._consecutive_losses[account_id] = self._consecutive_losses.get(account_id, 0) + 1
        elif pnl > 0:
            self._consecutive_losses[account_id] = 0

    def reset_account(self, account_id: str) -> None:
        self._last_order_at.pop(account_id, None)
        self._consecutive_losses.pop(account_id, None)

    def position_size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float,
        risk_pct: float | None = None,
        max_notional_pct: float | None = None,
    ) -> float:
        if equity <= 0 or entry_price <= 0 or stop_price <= 0:
            raise ValueError("equity, entry_price and stop_price must be positive")
        risk_budget = equity * (risk_pct if risk_pct is not None else self.max_risk_per_trade_pct) / 100
        distance = abs(entry_price - stop_price)
        if distance == 0:
            raise ValueError("stop_price must differ from entry_price")
        by_risk = risk_budget / distance
        notional_cap = equity * (max_notional_pct if max_notional_pct is not None else self.max_notional_pct) / 100
        by_notional = notional_cap / entry_price
        return max(0.0, min(by_risk, by_notional))

    def check(
        self,
        order: OrderRequest,
        snapshot: AccountSnapshot | None,
        *,
        current_price: float | None = None,
        stop_price: float | None = None,
        spread_pct: float | None = None,
        expected_fill_price: float | None = None,
        market_data_age_seconds: float | None = None,
        current_total_exposure: float = 0.0,
        current_symbol_exposure: float = 0.0,
    ) -> RiskDecision:
        if snapshot is None:
            return RiskDecision(False, "risk snapshot is unavailable")
        if snapshot.equity <= 0:
            return RiskDecision(False, "account equity must be positive")
        if snapshot.daily_loss_pct >= self.max_daily_loss_pct:
            return RiskDecision(False, "daily loss limit reached")
        if self.max_consecutive_losses and self._consecutive_losses.get(snapshot.account_id, 0) >= self.max_consecutive_losses:
            return RiskDecision(False, "consecutive loss limit reached")
        if snapshot.open_positions >= self.max_open_positions and order.side == OrderSide.BUY:
            return RiskDecision(False, "maximum open positions reached")

        price = expected_fill_price or current_price
        if price is None or price <= 0:
            return RiskDecision(False, "market price is required for risk validation")
        if market_data_age_seconds is not None and market_data_age_seconds > self.max_market_data_age_seconds:
            return RiskDecision(False, "market data is stale")

        notional = order.quantity * price
        if notional > snapshot.equity * self.max_notional_pct / 100:
            return RiskDecision(False, "maximum position notional exceeded")
        if self.max_order_notional_usdt is not None and notional > self.max_order_notional_usdt:
            return RiskDecision(False, "absolute order notional cap exceeded")

        if order.side == OrderSide.BUY:
            if current_total_exposure + notional > snapshot.equity * self.max_total_exposure_pct / 100:
                return RiskDecision(False, "maximum total exposure exceeded")
            if current_symbol_exposure + notional > snapshot.equity * self.max_symbol_exposure_pct / 100:
                return RiskDecision(False, "maximum symbol exposure exceeded")

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

        if self.cooldown_seconds:
            last = self._last_order_at.get(snapshot.account_id)
            now = self._clock()
            if last is not None and now - last < self.cooldown_seconds:
                return RiskDecision(False, "order cooldown active")

        return RiskDecision(True, "risk checks passed")

    def assert_allowed(self, *args, **kwargs) -> None:
        decision = self.check(*args, **kwargs)
        if not decision.allowed:
            raise RuntimeError(decision.reason)
