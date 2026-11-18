from dataclasses import dataclass
from .models import PaperOrder, TradeSide

@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None

class PaperBroker:
    def __init__(self, cash: float):
        self.cash = cash
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0

    def buy(self, order: PaperOrder) -> Position:
        cost = order.quantity * order.price
        if cost > self.cash:
            raise ValueError("Insufficient paper cash")
        if order.symbol in self.positions:
            raise ValueError("Position already exists")
        self.cash -= cost
        position = Position(order.symbol, order.quantity, order.price, order.stop_loss, order.take_profit)
        self.positions[order.symbol] = position
        return position

    def sell(self, symbol: str, price: float) -> float:
        position = self.positions.pop(symbol)
        proceeds = position.quantity * price
        cost = position.quantity * position.entry_price
        pnl = proceeds - cost
        self.cash += proceeds
        self.realized_pnl += pnl
        return pnl

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(p.quantity * prices.get(s, p.entry_price) for s, p in self.positions.items())
