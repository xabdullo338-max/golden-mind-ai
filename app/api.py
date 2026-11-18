from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .account_manager import AccountManager
from .execution_gate import ExecutionGate
from .kill_switch import KillSwitch
from .order_models import OrderRequest, OrderSide, OrderType
from .portfolio_state import PortfolioStateManager

app = FastAPI(title="Golden Mind AI API", version="0.1.0")

accounts = AccountManager()
kill_switch = KillSwitch()
execution_gate = ExecutionGate()
portfolio_state = PortfolioStateManager()


class OrderBody(BaseModel):
    client_order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: OrderSide
    quantity: float = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = Field(default=None, gt=0)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "golden-mind-ai"}


@app.get("/accounts")
async def list_accounts():
    return accounts.list_accounts()


@app.get("/accounts/{account_id}/state")
async def account_state(account_id: str):
    state = portfolio_state.get(account_id)
    if state is None:
        raise HTTPException(status_code=404, detail="account state not found")
    return {
        "account_id": state.account_id,
        "broker": state.broker,
        "positions": state.positions,
        "open_orders": state.open_orders,
        "executions": state.executions,
        "confirmed": state.confirmed,
    }


@app.post("/kill-switch/stop")
async def stop_all():
    kill_switch.stop_all()
    return {"status": "stopped"}


@app.post("/kill-switch/resume")
async def resume():
    kill_switch.resume()
    return {"status": "resumed"}


@app.post("/accounts/{account_id}/disable")
async def disable_account(account_id: str):
    try:
        accounts.disable(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="account not found")
    kill_switch.disable_account(account_id)
    return {"account_id": account_id, "enabled": False}


@app.post("/accounts/{account_id}/enable")
async def enable_account(account_id: str):
    try:
        accounts.enable(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="account not found")
    kill_switch.enable_account(account_id)
    return {"account_id": account_id, "enabled": True}


@app.post("/accounts/{account_id}/orders")
async def place_order(account_id: str, body: OrderBody):
    state = portfolio_state.get(account_id)
    if state is None:
        raise HTTPException(status_code=409, detail="broker state is not reconciled")

    try:
        execution_gate.assert_ready(
            account_enabled=accounts.accounts[account_id].enabled,
            state_confirmed=state.confirmed,
            daily_loss_ok=True,
            live_enabled=False,
        )
    except (RuntimeError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    order = OrderRequest(
        client_order_id=body.client_order_id,
        symbol=body.symbol,
        side=body.side,
        quantity=body.quantity,
        order_type=body.order_type,
        limit_price=body.limit_price,
    )
    try:
        return await accounts.order_to(account_id, order)
    except (KeyError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
