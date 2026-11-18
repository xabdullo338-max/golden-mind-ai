from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from .market_data import MarketTick
from .order_models import OrderRequest, OrderSide
from .portfolio import AccountSnapshot
from .portfolio_risk import PortfolioRiskEngine
from .strategy import StrategyEngine

@dataclass(frozen=True)
class TradePlan:
    account_id: str
    symbol: str
    side: str
    entry_price: float
    stop_price: float
    quantity: float
    notional: float
    risk_amount: float
    strategy_reason: str
    client_order_id: str

class TradePlanner:
    """Converts a strategy signal into a risk-approved order plan."""

    def __init__(self, strategy: StrategyEngine | None = None, risk: PortfolioRiskEngine | None = None):
        self.strategy = strategy or StrategyEngine()
        self.risk = risk or PortfolioRiskEngine()

    def plan(self, account_id: str, tick: MarketTick, fast_price: float | None,
             slow_price: float | None, snapshot: AccountSnapshot, stop_price: float,
             max_notional: float | None = None) -> TradePlan | None:
        signal = self.strategy.generate(tick, fast_price, slow_price)
        if signal is None:
            return None
        decision = self.risk.evaluate(snapshot, entry_price=tick.price,
                                      stop_price=stop_price, max_notional=max_notional)
        if not decision.approved or decision.sizing is None:
            return None
        return TradePlan(
            account_id=account_id, symbol=signal.symbol, side=signal.side.value,
            entry_price=tick.price, stop_price=stop_price,
            quantity=decision.sizing.quantity, notional=decision.sizing.notional,
            risk_amount=decision.sizing.risk_amount, strategy_reason=signal.reason,
            client_order_id=f"gmai-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:10]}",
        )

    @staticmethod
    def to_order(plan: TradePlan) -> OrderRequest:
        return OrderRequest(
            client_order_id=plan.client_order_id,
            symbol=plan.symbol,
            side=OrderSide(plan.side),
            quantity=plan.quantity,
        )
