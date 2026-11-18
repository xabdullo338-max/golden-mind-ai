from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class RiskDecision(BaseModel):
    approved: bool
    reason: str
    risk_amount: float = Field(ge=0)
    quantity: float = Field(ge=0)

class PaperOrder(BaseModel):
    symbol: str
    side: TradeSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    stop_loss: float | None = None
    take_profit: float | None = None
    created_at: datetime = Field(default_factory=utc_now)

class Portfolio(BaseModel):
    cash: float = Field(ge=0)
    equity: float = Field(ge=0)
    realized_pnl: float = 0
    daily_pnl: float = 0
    open_positions: int = 0
