from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class PaperTrade:
    symbol: str
    side: str
    entry_price: float
    quantity: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    status: str = "OPEN"
    exit_price: Optional[float] = None
    pnl_usdt: Optional[float] = None


class PaperTrader:
    def __init__(self, initial_balance: float = 100.0):
        if initial_balance <= 0:
            raise ValueError("initial_balance must be greater than zero")
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.trades: list[PaperTrade] = []

    def open_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
    ) -> PaperTrade:
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if entry_price <= 0 or quantity <= 0:
            raise ValueError("entry_price and quantity must be greater than zero")

        trade = PaperTrade(
            symbol=symbol.upper(),
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self.trades.append(trade)
        return trade

    def close_trade(self, trade: PaperTrade, exit_price: float) -> PaperTrade:
        if trade.status != "OPEN":
            raise ValueError("trade is already closed")
        if exit_price <= 0:
            raise ValueError("exit_price must be greater than zero")

        if trade.side == "BUY":
            pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            pnl = (trade.entry_price - exit_price) * trade.quantity

        trade.exit_price = exit_price
        trade.pnl_usdt = round(pnl, 8)
        trade.status = "CLOSED"
        self.balance = round(self.balance + pnl, 8)
        return trade

    def snapshot(self):
        return {
            "initial_balance": self.initial_balance,
            "balance": self.balance,
            "pnl": round(self.balance - self.initial_balance, 8),
            "trades": [asdict(t) for t in self.trades],
        }
