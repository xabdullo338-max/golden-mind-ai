from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
from .runtime import build_binance_runtime, start_binance_runtime, stop_binance_runtime
from .live_strategy import LiveStrategyRunner
from .strategy_engine import AdaptiveEnsembleStrategy, Candle
from .storage import data_path

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
journal = TradingJournal(data_path("golden_mind_ai.db"))

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
    daily_risk_store=DailyRiskStateStore(data_path("golden_mind_risk.db")),
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

runtime = None
strategy_task = None
strategy_engine = AdaptiveEnsembleStrategy()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runtime, strategy_task
    if settings.trading_mode.upper() in {"PAPER", "TESTNET", "LIVE"}:
        runtime = build_binance_runtime(
            settings, accounts, portfolio_state, event_bus, journal,
            positions=positions, market_data=market_data,
            emergency=emergency, pending_orders=pending_orders,
        )
        await start_binance_runtime(runtime)
        if settings.live_trading_enabled and runtime.adapter.account.mode == "LIVE":
            import asyncio
            runner = LiveStrategyRunner(
                settings=settings,
                accounts=accounts,
                router=order_router,
                portfolio_state=portfolio_state,
                risk_engine=risk_engine,
                market_data=market_data,
                strategy=AdaptiveEnsembleStrategy(),
            )
            strategy_task = asyncio.create_task(runner.run_forever())
    yield
    if strategy_task is not None:
        strategy_task.cancel()
        try:
            await strategy_task
        except asyncio.CancelledError:
            pass
    if runtime is not None:
        await stop_binance_runtime(runtime)


app = FastAPI(title="Golden Mind AI", version="1.0.0", lifespan=lifespan)


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
        "accounts": len(accounts.accounts),
    }


@app.post("/token")
async def token(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        user = authenticate(form_data.username, form_data.password)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Authentication storage is unavailable") from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    scopes = role_scopes(user["role"])
    return {
        "access_token": create_access_token(user["username"], scopes),
        "token_type": "bearer",
    }


@app.get("/protected/ping")
async def protected_ping(_: dict = Depends(require_scope("read"))):
    return {"status": "ok"}


@app.get("/accounts")
async def list_accounts(_: dict = Depends(require_scope("read"))):
    return {"accounts": accounts.list_accounts()}


@app.get("/accounts/{account_id}/state")
async def account_state(account_id: str, _: dict = Depends(require_scope("read"))):
    managed = accounts.accounts.get(account_id)
    if managed is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    state = portfolio_state.get(account_id)
    if state is None:
        return {
            "account_id": account_id,
            "broker": managed.adapter.account.broker,
            "balances": {},
            "positions": {},
            "confirmed": False,
        }

    return {
        "account_id": state.account_id,
        "broker": state.broker,
        "balances": state.balances,
        "positions": state.positions,
        "confirmed": state.confirmed,
    }



@app.get("/market")
async def market(symbol: str = "BTCUSDT", _: dict = Depends(require_scope("read"))):
    managed = accounts.accounts.get(settings.binance_account_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="Binance account is not registered")
    tick = await managed.adapter.get_market_tick(symbol.upper())
    if tick is None:
        raise HTTPException(status_code=503, detail=f"Market data unavailable for {symbol.upper()}")
    return {
        "broker": tick.broker,
        "symbol": tick.symbol,
        "price": tick.price,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread_pct": tick.spread_pct,
        "volume": tick.volume,
        "timestamp": tick.timestamp.isoformat(),
    }

@app.get("/portfolio")
async def portfolio(_: dict = Depends(require_scope("read"))):
    state = portfolio_state.get(settings.binance_account_id)
    if state is None:
        raise HTTPException(status_code=503, detail="Portfolio state unavailable")
    return {
        "account_id": state.account_id,
        "broker": state.broker,
        "balances": state.balances,
        "positions": state.positions,
        "confirmed": state.confirmed,
    }

@app.get("/risk/snapshot")
async def risk_snapshot(_: dict = Depends(require_scope("read"))):
    state = portfolio_state.get(settings.binance_account_id)
    if state is None or not state.confirmed:
        raise HTTPException(status_code=503, detail="Reconciled portfolio state unavailable")
    prices = market_data.price_map("BINANCE")
    snapshot = risk_snapshot_provider.build(state, prices=prices)
    if snapshot is None:
        raise HTTPException(status_code=503, detail="Risk snapshot unavailable")
    return {
        "account_id": snapshot.account_id,
        "equity": snapshot.equity,
        "cash": snapshot.cash,
        "realized_pnl": snapshot.realized_pnl,
        "unrealized_pnl": snapshot.unrealized_pnl,
        "daily_start_equity": snapshot.daily_start_equity,
        "daily_loss_pct": snapshot.daily_loss_pct,
        "open_positions": snapshot.open_positions,
        "limits": {
            "risk_per_trade_pct": risk_engine.max_risk_per_trade_pct,
            "daily_loss_pct": risk_engine.max_daily_loss_pct,
            "max_open_positions": risk_engine.max_open_positions,
        },
    }

@app.get("/orders/history")
async def orders_history(_: dict = Depends(require_scope("read"))):
    lifecycle = order_router.lifecycle
    return {"orders": [
        {
            "broker": item.broker,
            "account_id": item.account_id,
            "client_order_id": item.client_order_id,
            "status": item.status.value,
            "symbol": item.symbol,
            "executed_quantity": item.executed_quantity,
            "average_price": item.average_price,
            "broker_order_id": item.broker_order_id,
            "side": item.side,
            "last_fill_quantity": item.last_fill_quantity,
            "last_fill_price": item.last_fill_price,
        }
        for item in lifecycle.snapshot()
    ] if lifecycle is not None else []}


@app.get("/strategy/signal")
async def strategy_signal(symbol: str = "BTCUSDT", _: dict = Depends(require_scope("read"))):
    managed = accounts.accounts.get(settings.binance_account_id)
    if managed is None:
        raise HTTPException(status_code=404, detail="Binance account is not registered")
    rows = await managed.adapter.get_candles(symbol.upper(), "1m", 60)
    if len(rows) < 45:
        raise HTTPException(status_code=503, detail="Not enough candles for strategy evaluation")
    decision = strategy_engine.evaluate([Candle(**row) for row in rows])
    indicators = decision.indicators
    return {
        "symbol": symbol.upper(),
        "signal": decision.signal.value,
        "confidence": decision.confidence,
        "regime": decision.regime.value,
        "model_score": decision.model_score,
        "ai_probability": decision.ai_probability,
        "stop_price": decision.stop_price,
        "take_profit_price": decision.take_profit_price,
        "reason": decision.reason,
        "indicators": {
            "ema_fast": indicators.ema_fast if indicators else None,
            "ema_slow": indicators.ema_slow if indicators else None,
            "rsi": indicators.rsi if indicators else None,
            "atr_pct": indicators.atr_pct if indicators else None,
            "adx": indicators.adx if indicators else None,
            "volume_ratio": indicators.volume_ratio if indicators else None,
            "momentum_pct": indicators.momentum_pct if indicators else None,
        },
    }

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
        account_id = payload.metadata.get("account_id") or settings.binance_account_id
        return await order_router.route(str(account_id), order)
    except (ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.websocket("/ws/events")
async def events_socket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    try:
        if not token:
            await websocket.close(code=4401)
            return
        from .auth import decode_access_token
        claims = decode_access_token(token)
        if "read" not in claims.get("scopes", []):
            await websocket.close(code=4403)
            return
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    queue = event_bus.subscribe()
    try:
        await websocket.send_json({"event_type": "connected", "payload": {"trading_mode": settings.trading_mode.upper()}})
        while True:
            event = await queue.get()
            await websocket.send_json(EventBus.serialize(event))
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(queue)

@app.post("/kill-switch/stop")
async def stop(_: dict = Depends(require_scope("admin"))):
    kill_switch.stop_all()
    return {"status": "stopped"}


@app.post("/kill-switch/reset")
async def reset(_: dict = Depends(require_scope("admin"))):
    kill_switch.resume()
    return {"status": "reset"}
