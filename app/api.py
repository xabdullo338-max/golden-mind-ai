from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from .account_manager import AccountManager
from .auth import authenticate, create_access_token, require_scope, role_scopes
from .config import Settings
from .event_bus import EventBus, TradingEvent
from .execution_gate import ExecutionGate
from .journal import TradingJournal
from .kill_switch import KillSwitch
from .order_models import OrderRequest, OrderSide, OrderType
from .order_router import OrderRouter
from .portfolio_state import PortfolioStateManager
from .risk_engine import RiskEngine
from .risk_snapshot import RiskSnapshotProvider
from .runtime import build_binance_runtime, start_binance_runtime, stop_binance_runtime
from .ws import install_websocket_routes


settings = Settings()
accounts = AccountManager()
kill_switch = KillSwitch()
execution_gate = ExecutionGate()
portfolio_state = PortfolioStateManager()
event_bus = EventBus()
journal = TradingJournal("data/golden_mind_ai.db")
risk_engine = RiskEngine(
    max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
    max_daily_loss_pct=settings.max_daily_loss_pct,
    max_open_positions=settings.max_open_positions,
    max_total_exposure_pct=settings.max_total_exposure_pct,
    max_symbol_exposure_pct=settings.max_symbol_exposure_pct,
    max_market_data_age_seconds=settings.max_market_data_age_seconds,
    max_spread_pct=settings.scalping_max_spread_pct,
    cooldown_seconds=settings.risk_cooldown_seconds,
    max_consecutive_losses=settings.max_consecutive_losses,
)
risk_snapshot_provider = RiskSnapshotProvider()

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
)
