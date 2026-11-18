from __future__ import annotations

from dataclasses import dataclass

from .market_data import MarketTick
from .order_models import OrderRequest, OrderSide

@dataclass(frozen=True)
class StrategySignal:
    symbol: str
    side: OrderSide
    quantity: float
    reason: str

class StrategyEngine:
    """Small deterministic strategy boundary; AI strategies plug in here later."""

    def generate(self, tick: MarketTick, fast_price: float | None, slow_price: float | None) -> StrategySignal | None:
        if fast_price is None or slow_price is None:
            return None
        if fast_price > slow_price:
            return StrategySignal(tick.symbol, OrderSide.BUY, 0.0, "fast_above_slow")
        if fast_price < slow_price:
            return StrategySignal(tick.symbol, OrderSide.SELL, 0.0, "fast_below_slow")
        return None

    def to_order(self, signal: StrategySignal, client_order_id: str) -> OrderRequest:
        if signal.quantity <= 0:
            raise ValueError("strategy signal quantity must be positive")
        return OrderRequest(client_order_id, signal.symbol, signal.side, signal.quantity)
