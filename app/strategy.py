from dataclasses import dataclass
from typing import Literal, Optional

Signal = Literal["BUY", "SELL", "HOLD"]


@dataclass
class StrategyConfig:
    rsi_buy_max: float = 35.0
    rsi_sell_min: float = 65.0
    stop_loss_pct: float = 0.8
    take_profit_pct: float = 1.6


def generate_signal(
    ema20: Optional[float],
    ema50: Optional[float],
    rsi14: Optional[float],
) -> Signal:
    if ema20 is None or ema50 is None or rsi14 is None:
        return "HOLD"

    if ema20 > ema50 and rsi14 <= 35:
        return "BUY"

    if ema20 < ema50 and rsi14 >= 65:
        return "SELL"

    return "HOLD"


def risk_levels(
    price: float,
    signal: Signal,
    config: StrategyConfig | None = None,
):
    cfg = config or StrategyConfig()

    if price <= 0:
        raise ValueError("price must be greater than zero")

    if signal == "BUY":
        return {
            "stop_loss": round(
                price * (1 - cfg.stop_loss_pct / 100), 8
            ),
            "take_profit": round(
                price * (1 + cfg.take_profit_pct / 100), 8
            ),
        }

    if signal == "SELL":
        return {
            "stop_loss": round(
                price * (1 + cfg.stop_loss_pct / 100), 8
            ),
            "take_profit": round(
                price * (1 - cfg.take_profit_pct / 100), 8
            ),
        }

    return {
        "stop_loss": None,
        "take_profit": None,
    }


def position_size(
    balance_usdt: float,
    entry_price: float,
    risk_pct: float = 1.0,
    stop_loss_pct: float = 0.8,
    max_position_pct: float = 25.0,
) -> float:
    if balance_usdt <= 0 or entry_price <= 0:
        return 0.0

    if risk_pct <= 0 or stop_loss_pct <= 0:
        return 0.0

    risk_amount = balance_usdt * risk_pct / 100

    quantity = risk_amount / (
        entry_price * stop_loss_pct / 100
    )

    max_notional = (
        balance_usdt * max_position_pct / 100
    )

    quantity = min(
        quantity,
        max_notional / entry_price,
    )

    return round(quantity, 8)
