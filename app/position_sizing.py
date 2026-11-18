from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class PositionSizing:
    quantity: float
    risk_amount: float
    notional: float

def size_position(equity: float, entry_price: float, stop_price: float, risk_pct: float, max_notional: float | None = None) -> PositionSizing:
    if equity <= 0 or entry_price <= 0 or stop_price <= 0:
        raise ValueError("equity, entry_price and stop_price must be positive")
    if not 0 < risk_pct <= 2:
        raise ValueError("risk_pct must be > 0 and <= 2")
    distance = abs(entry_price - stop_price)
    if distance == 0:
        raise ValueError("entry_price and stop_price must differ")
    risk_amount = equity * risk_pct / 100
    quantity = risk_amount / distance
    notional = quantity * entry_price
    if max_notional is not None:
        if max_notional <= 0:
            raise ValueError("max_notional must be positive")
        if notional > max_notional:
            quantity = max_notional / entry_price
            notional = max_notional
            risk_amount = quantity * distance
    return PositionSizing(quantity, risk_amount, notional)
