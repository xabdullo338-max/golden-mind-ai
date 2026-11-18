from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .event_bus import EventBus, TradingEvent
from .order_models import OrderRequest, OrderSide
from .scalping_engine import ScalpingEngine
from .trade_planner import TradePlanner
from .portfolio_risk import PortfolioRiskEngine

@dataclass(frozen=True)
class ScalpExecutionResult:
    submitted: bool
    reason: str
    order: OrderRequest | None = None
    broker_result: dict[str, Any] | None = None

class ScalpExecutionPipeline:
    """Connects market signals to risk/planning and broker execution.

    The pipeline records the rate-limit only after the broker accepts the
    submission. It never creates an order merely to satisfy the hourly target.
    """

    def __init__(self, accounts, account_snapshots, kill_switch=None,
                 event_bus: EventBus | None = None,
                 scalping_engine: ScalpingEngine | None = None):
        self.accounts = accounts
        self.account_snapshots = account_snapshots
        self.kill_switch = kill_switch
        self.event_bus = event_bus or EventBus()
        self.scalping_engine = scalping_engine or ScalpingEngine()
        self.trade_planners: dict[str, TradePlanner] = {}

    def _planner(self, account_id: str) -> TradePlanner:
        if account_id not in self.trade_planners:
            self.trade_planners[account_id] = TradePlanner(
                strategy=None,
                risk=PortfolioRiskEngine(max_daily_loss_pct=3.0,
                                         max_risk_per_trade_pct=0.25),
            )
        return self.trade_planners[account_id]

    async def on_tick(self, account_id: str, tick, reference_price: float,
                      stop_price: float, max_notional: float | None = None) -> ScalpExecutionResult:
        if account_id not in self.accounts.accounts:
            return ScalpExecutionResult(False, "unknown account")
        if not self.accounts.accounts[account_id].enabled:
            return ScalpExecutionResult(False, "account disabled")
        if self.kill_switch:
            self.kill_switch.assert_allowed(account_id)

        signal = self.scalping_engine.generate(account_id, tick, reference_price)
        if signal is None:
            return ScalpExecutionResult(False, "market filter rejected signal")

        limiter = self.scalping_engine.limiter(account_id)
        decision = limiter.check()
        if not decision.allowed:
            return ScalpExecutionResult(False, decision.reason)

        snapshot = self.account_snapshots.get(account_id)
        if snapshot is None:
            return ScalpExecutionResult(False, "account snapshot unavailable")

        planner = self._planner(account_id)
        plan = planner.plan(
            account_id=account_id,
            tick=tick,
            fast_price=tick.price,
            slow_price=reference_price,
            snapshot=snapshot,
            stop_price=stop_price,
            max_notional=max_notional,
        )
        if plan is None:
            return ScalpExecutionResult(False, "risk/strategy rejected trade")

        order = planner.to_order(plan)
        result = await self.accounts.order_to(account_id, order)
        limiter.record()
        await self.event_bus.publish(
            TradingEvent.create(
                "SCALP_ORDER_SUBMITTED",
                account_id,
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
                reason=signal.reason,
                trades_last_hour=limiter.count_last_hour(),
            )
        )
        return ScalpExecutionResult(True, "submitted", order, result)
