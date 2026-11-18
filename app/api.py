from __future__ import annotations
import os
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from .account_manager import AccountManager
from .auth import authenticate, create_access_token, require_scope, role_scopes
from .event_bus import EventBus, TradingEvent
from .execution_gate import ExecutionGate
from .kill_switch import KillSwitch
from .order_models import OrderRequest, OrderSide, OrderType
from .portfolio_state import PortfolioStateManager
from .ws import install_websocket_routes

app = FastAPI(title="Golden Mind AI API", version="0.3.0")
accounts = AccountManager()
kill_switch = KillSwitch()
execution_gate = ExecutionGate()
portfolio_state = PortfolioStateManager()
event_bus = EventBus()
install_websocket_routes(app, event_bus)

class OrderBody(BaseModel):
    client_order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: OrderSide
    quantity: float = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)

@app.post("/token")
async def token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = authenticate(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    scopes = role_scopes(user["role"])
    requested = set(form_data.scopes)
    if requested and not requested.issubset(scopes):
        raise HTTPException(status_code=400, detail="Requested scope is not allowed")
    return {"access_token": create_access_token(user["username"], scopes),
            "token_type": "bearer", "username": user["username"], "role": user["role"]}

@app.get("/protected/ping")
async def protected_ping(_: dict = Depends(require_scope("read"))):
    return {"status": "authenticated"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "golden-mind-ai",
            "event_subscribers": event_bus.subscriber_count}

@app.get("/accounts")
async def list_accounts(_: dict = Depends(require_scope("read"))):
    return accounts.list_accounts()

@app.get("/accounts/{account_id}/state")
async def account_state(account_id: str, _: dict = Depends(require_scope("read"))):
    state = portfolio_state.get(account_id)
    if state is None:
        raise HTTPException(status_code=404, detail="account state not found")
    return {"account_id": state.account_id, "broker": state.broker,
            "positions": state.positions, "open_orders": state.open_orders,
            "executions": state.executions, "confirmed": state.confirmed}

@app.post("/kill-switch/stop")
async def stop_all(_: dict = Depends(require_scope("admin"))):
    kill_switch.stop_all()
    await event_bus.publish(TradingEvent.create("KILL_SWITCH", payload="STOP_ALL"))
    return {"status": "stopped"}

@app.post("/kill-switch/resume")
async def resume(_: dict = Depends(require_scope("admin"))):
    kill_switch.resume()
    await event_bus.publish(TradingEvent.create("KILL_SWITCH", payload="RESUMED"))
    return {"status": "resumed"}

@app.post("/accounts/{account_id}/disable")
async def disable_account(account_id: str, _: dict = Depends(require_scope("admin"))):
    try:
        accounts.disable(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="account not found")
    kill_switch.disable_account(account_id)
    await event_bus.publish(TradingEvent.create("ACCOUNT_DISABLED", account_id))
    return {"account_id": account_id, "enabled": False}

@app.post("/accounts/{account_id}/enable")
async def enable_account(account_id: str, _: dict = Depends(require_scope("admin"))):
    try:
        accounts.enable(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="account not found")
    kill_switch.enable_account(account_id)
    await event_bus.publish(TradingEvent.create("ACCOUNT_ENABLED", account_id))
    return {"account_id": account_id, "enabled": True}

def _execution_mode_allowed(account) -> bool:
    # Non-real-money modes are allowed; LIVE needs an explicit global safety flag.
    if account.mode in {"PAPER", "TESTNET", "DEMO"}:
        return True
    return account.mode == "LIVE" and os.getenv("GMAI_LIVE_TRADING", "false").lower() in {"1", "true", "yes"}

@app.post("/accounts/{account_id}/orders")
async def place_order(account_id: str, body: OrderBody, _: dict = Depends(require_scope("trade"))):
    managed = accounts.accounts.get(account_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="account not found")
    state = portfolio_state.get(account_id)
    if state is None or not state.confirmed:
        raise HTTPException(status_code=409, detail="broker state is not reconciled")

    try:
        execution_gate.assert_ready(
            account_enabled=managed.enabled,
            state_confirmed=state.confirmed,
            # Until a real AccountSnapshot provider is injected, never claim
            # that LIVE has passed the daily-loss gate.
            daily_loss_ok=managed.adapter.account.mode != "LIVE",
            live_enabled=_execution_mode_allowed(managed.adapter.account),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    order = OrderRequest(client_order_id=body.client_order_id, symbol=body.symbol,
                         side=body.side, quantity=body.quantity,
                         order_type=body.order_type, limit_price=body.limit_price,
                         metadata={"price": body.price} if body.price else {})
    try:
        result = await accounts.order_to(account_id, order)
    except (KeyError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await event_bus.publish(TradingEvent.create("ORDER_SUBMITTED", account_id,
        symbol=body.symbol, side=body.side.value, quantity=body.quantity,
        order_type=body.order_type.value, mode=managed.adapter.account.mode))
    return result
