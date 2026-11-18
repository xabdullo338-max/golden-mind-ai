from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Fill:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float = 0.0

    def __post_init__(self):
        if self.quantity <= 0 or self.price <= 0 or self.commission < 0:
            raise ValueError("invalid fill values")

@dataclass(frozen=True)
class RealizedPnL:
    symbol: str
    quantity: float
    gross_pnl: float
    commission: float
    net_pnl: float

class FillLedger:
    def __init__(self):
        self._fills: list[Fill] = []

    def add(self, fill: Fill) -> None:
        self._fills.append(fill)

    def fills(self) -> list[Fill]:
        return list(self._fills)

    def realized_pnl(self, symbol: str) -> RealizedPnL:
        buys = [f for f in self._fills if f.symbol == symbol and f.side.upper() == "BUY"]
        sells = [f for f in self._fills if f.symbol == symbol and f.side.upper() == "SELL"]
        buy_qty = sum(f.quantity for f in buys)
        sell_qty = sum(f.quantity for f in sells)
        matched = min(buy_qty, sell_qty)
        avg_buy = sum(f.quantity * f.price for f in buys) / buy_qty if buy_qty else 0.0
        avg_sell = sum(f.quantity * f.price for f in sells) / sell_qty if sell_qty else 0.0
        gross = matched * (avg_sell - avg_buy)
        commission = sum(f.commission for f in self._fills if f.symbol == symbol)
        return RealizedPnL(symbol, matched, gross, commission, gross - commission)
