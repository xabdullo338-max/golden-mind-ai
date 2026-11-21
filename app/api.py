from __future__ import annotations

from .account_manager import AccountManager
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

settings = Settings()
accounts = AccountManager()
kill_switch = KillSwitch()
execution_gate = ExecutionGate()
portfolio_state = PortfolioStateManager()
positions = PositionEngine()
market_data = MarketDataStore()
emergency = EmergencySafetySystem(accounts, kill_switch, event_bus)
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
)
