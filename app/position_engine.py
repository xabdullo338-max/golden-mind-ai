from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Side = Literal["BUY", "SELL"]

@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    average_entry: float = 0.0
    realized_pnl: float = 0.0

    def apply_fill(self, side: Side, quantity: float, price: float, commission: float = 0.0) -> None:
        if quantity <= 0 or price <= 0 or commission < 0:
            raise ValueError("invalid fill")
        side = side.upper()
        if side == "BUY":
            new_qty = self.quantity + quantity
            if new_qty <= 0:
                raise RuntimeError("invalid resulting quantity")
            self.average_entry = (
                (self.quantity * self.average_entry) + (quantity * price)
            ) / new_qty
            self.quantity = new_qty
            self.realized_pnl -= commission
            return
        if side != "SELL":
            raise ValueError("side must be BUY or SELL")

        closing = min(quantity, max(self.quantity, 0.0))
        self.realized_pnl += closing * (price - self.average_entry) - commission

        if quantity <= self.quantity:
            self.quantity -= quantity
            if self.quantity == 0:
                self.average_entry = 0.0
            return

        # Long-only accounting: a sell larger than the current long opens
        # no short position. The excess is rejected until short accounting is added.
        raise RuntimeError("sell quantity exceeds long position")

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.quantity <= 0:
            return 0.0
        return self.quantity * (mark_price - self.average_entry)

class PositionEngine:
    def __init__(self):
        self._positions: dict[tuple[str, str], Position] = {}

    def get(self, account_id: str, symbol: str) -> Position:
        key = (account_id, symbol.upper())
        if key not in self._positions:
            self._positions[key] = Position(symbol=symbol.upper())
        return self._positions[key]

    def apply_fill(
        self,
        account_id: str,
        symbol: str,
        side: Side,
        quantity: float,
        price: float,
        commission: float = 0.0,
    ) -> Position:
        position = self.get(account_id, symbol)
        position.apply_fill(side, quantity, price, commission)
        return position

    def snapshot(self, account_id: str) -> list[Position]:
        return [
            p for (aid, _), p in self._positions.items()
            if aid == account_id and p.quantity > 0
        ]
