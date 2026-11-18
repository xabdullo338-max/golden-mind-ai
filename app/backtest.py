from dataclasses import dataclass

@dataclass
class BacktestResult:
    initial_balance: float
    final_balance: float
    total_return_pct: float
    trades: int
    win_rate_pct: float
    max_drawdown_pct: float

def run_simple_backtest(prices: list[float], initial_balance: float = 300.0) -> BacktestResult:
    if len(prices) < 3:
        raise ValueError("At least 3 prices are required")
    cash = initial_balance
    entry = None
    wins = 0
    trades = 0
    peak = initial_balance
    max_dd = 0.0

    for i in range(2, len(prices)):
        fast = sum(prices[i-1:i+1]) / 2
        slow = sum(prices[max(0, i-2):i+1]) / min(3, i+1)
        if entry is None and fast > slow:
            entry = prices[i]
            cash -= entry
        elif entry is not None and fast < slow:
            cash += prices[i]
            trades += 1
            wins += prices[i] > entry
            entry = None
        equity = cash + (entry if entry is not None else 0)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)

    if entry is not None:
        cash += prices[-1]
        trades += 1
        wins += prices[-1] > entry

    return BacktestResult(
        initial_balance=initial_balance,
        final_balance=round(cash, 2),
        total_return_pct=round((cash / initial_balance - 1) * 100, 2),
        trades=trades,
        win_rate_pct=round((wins / trades) * 100, 2) if trades else 0,
        max_drawdown_pct=round(max_dd, 2),
    )
