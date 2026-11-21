from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from .account_manager import AccountManager
from .auth import authenticate, create_access_token, require_scope, role_scopes
from .config import Settings
from .daily_risk_state import DailyRiskStateStore
from .event_bus import EventBus
from .execution_gate import ExecutionGate
from .journal import TradingJournal
from .kill_switch import KillSwitch, EmergencySafetySystem
from .market_data_store import MarketDataStore
from .order_router import OrderRouter
from .portfolio_state import PortfolioStateManager
from .risk_engine import RiskEngine
from .risk_snapshot import RiskSnapshotProvider
from .position_engine import PositionEngine
from .pending_orders import PendingOrderStore

settings = Settings()
accounts = AccountManager()
kill_switch = KillSwitch()
execution_gate = ExecutionGate(
    live_trading_enabled=settings.live_trading_enabled,
)
portfolio_state = PortfolioStateManager()
positions = PositionEngine()
market_data = MarketDataStore()
pending_orders = PendingOrderStore()
event_bus = EventBus()
emergency = EmergencySafetySystem(accounts, kill_switch, event_bus)
journal = TradingJournal("data/golden_mind_ai.db")

risk_engine = RiskEngine(
    max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
    max_daily_loss_pct=min(settings.max_daily_loss_pct, settings.live_max_daily_loss_pct)
    if settings.live_trading_enabled else settings.max_daily_loss_pct,
    max_open_positions=settings.max_open_positions,
    max_total_exposure_pct=settings.max_total_exposure_pct,
    max_symbol_exposure_pct=settings.max_symbol_exposure_pct,
    max_market_data_age_seconds=settings.max_market_data_age_seconds,
    max_order_notional_usdt=settings.live_max_order_notional_usdt if settings.live_trading_enabled else None,
    max_spread_pct=settings.scalping_max_spread_pct,
    cooldown_seconds=settings.risk_cooldown_seconds,
    max_consecutive_losses=settings.max_consecutive_losses,
)

risk_snapshot_provider = RiskSnapshotProvider(
    daily_risk_store=DailyRiskStateStore(),
    positions=positions,
)


async def _market_tick(account_id: str, symbol: str):
    managed = accounts.accounts.get(account_id)
    if managed is None:
        return None
    return await managed.adapter.get_market_tick(symbol)


order_router = OrderRouter(
    accounts,
    kill_switch=kill_switch,
    execution_gate=execution_gate,
    portfolio_state=portfolio_state,
    risk_engine=risk_engine,
    risk_snapshot_provider=risk_snapshot_provider,
    market_tick_provider=_market_tick,
    market_data_store=market_data,
    emergency=emergency,
    pending_orders=pending_orders,
)

app = FastAPI(title="Golden Mind AI", version="1.0.0")


class OrderIn(BaseModel):
    client_order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: str
    quantity: float = Field(gt=0)
    order_type: str = "MARKET"
    limit_price: float | None = Field(default=None, gt=0)
    metadata: dict = Field(default_factory=dict)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "golden-mind-ai",
        "trading_mode": settings.trading_mode.upper(),
        "live_enabled": execution_gate.live_trading_enabled,
    }


@app.post("/token")
async def token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    scopes = role_scopes(user["role"])
    return {
        "access_token": create_access_token(user["username"], scopes),
        "token_type": "bearer",
    }


@app.get("/accounts")
async def list_accounts(_: dict = Depends(require_scope("read"))):
    return {"accounts": accounts.list_accounts()}


@app.get("/risk")
async def risk(_: dict = Depends(require_scope("read"))):
    return {
        "max_risk_per_trade_pct": risk_engine.max_risk_per_trade_pct,
        "max_daily_loss_pct": risk_engine.max_daily_loss_pct,
        "max_open_positions": risk_engine.max_open_positions,
        "max_total_exposure_pct": risk_engine.max_total_exposure_pct,
        "max_symbol_exposure_pct": risk_engine.max_symbol_exposure_pct,
        "live_trading_enabled": execution_gate.live_trading_enabled,
    }


@app.post("/orders/test")
async def test_order(payload: OrderIn, _: dict = Depends(require_scope("trade"))):
    from .order_models import OrderRequest, OrderSide, OrderType
    try:
        side = OrderSide(payload.side.upper())
        order_type = OrderType(payload.order_type.upper())
        order = OrderRequest(
            client_order_id=payload.client_order_id,
            symbol=payload.symbol.upper(),
            side=side,
            quantity=payload.quantity,
            order_type=order_type,
            limit_price=payload.limit_price,
            metadata=payload.metadata,
        )
        return await order_router.route(settings.binance_account_id, order)
    except (ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/kill-switch/stop")
async def stop(_: dict = Depends(require_scope("admin"))):
    kill_switch.stop_all()
    return {"status": "stopped"}


@app.post("/kill-switch/reset")
async def reset(_: dict = Depends(require_scope("admin"))):
    kill_switch.resume()
    return {"status": "reset"}
