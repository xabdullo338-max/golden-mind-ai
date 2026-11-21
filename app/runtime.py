from __future__ import annotations

from dataclasses import dataclass

from .account_manager import AccountManager
from .binance_execution_bridge import BinanceExecutionBridge
from .binance_ws import BinanceWebSocketClient, BinanceWebSocketConfig
from .brokers.binance import BinanceAdapter
from .config import Settings
from .event_bus import EventBus
from .execution_coordinator import ExecutionCoordinator
from .execution_ledger import ExecutionLedger
from .journal import TradingJournal
from .order_lifecycle import OrderLifecycle
from .portfolio_state import PortfolioStateManager
from .position_engine import PositionEngine
from .recovery import BrokerRecovery


@dataclass
class BinanceRuntime:
    account_id: str
    adapter: BinanceAdapter
    bridge: BinanceExecutionBridge
    websocket: BinanceWebSocketClient
    recovery: BrokerRecovery
    coordinator: ExecutionCoordinator


def _ws_url(base_url: str) -> str:
    if "testnet.binance.vision" in base_url:
        return "wss://ws-api.testnet.binance.vision/ws-api/v3"
    return "wss://ws-api.binance.com:443/ws-api/v3"


def build_binance_runtime(
    settings: Settings,
    accounts: AccountManager,
    portfolio_state: PortfolioStateManager,
    event_bus: EventBus,
    journal: TradingJournal,
) -> BinanceRuntime:
    mode = settings.trading_mode.upper()
    if mode not in {"PAPER", "TESTNET", "DEMO", "LIVE"}:
        raise ValueError(f"Unsupported trading mode: {mode}")

    adapter = BinanceAdapter(
        account_id=settings.binance_account_id,
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
        base_url=settings.binance_base_url,
        mode=mode,
        initial_quote_balance=settings.initial_balance_usdt,
        reconciliation_symbols=tuple(sorted(settings.symbols)),
    )
    accounts.register(adapter)

    coordinator = ExecutionCoordinator(
        OrderLifecycle(),
        journal,
        event_bus,
        positions=PositionEngine(),
        execution_ledger=ExecutionLedger(),
    )
    recovery = BrokerRecovery(accounts, portfolio_state, journal)
    bridge = BinanceExecutionBridge(
        settings.binance_account_id,
        coordinator,
        portfolio_state=portfolio_state,
        recovery=recovery,
    )

    websocket = BinanceWebSocketClient(
        config=BinanceWebSocketConfig(url=_ws_url(settings.binance_base_url)),
        event_bus=event_bus,
        on_disconnect=bridge.mark_disconnected,
        on_recovered=bridge.mark_reconnected_and_recover,
    )
    return BinanceRuntime(
        settings.binance_account_id, adapter, bridge, websocket, recovery, coordinator
    )


async def start_binance_runtime(runtime: BinanceRuntime) -> None:
    if runtime.adapter.account.mode == "PAPER":
        await runtime.recovery.recover_account(runtime.account_id)
        return

    if not runtime.adapter.api_key or not runtime.adapter.api_secret:
        runtime.bridge.mark_disconnected()
        return

    result = await runtime.recovery.recover_account(runtime.account_id)
    if not result.confirmed:
        return

    await runtime.websocket.start(
        handler=runtime.bridge.handle,
        api_key=runtime.adapter.api_key,
        api_secret=runtime.adapter.api_secret,
    )


async def stop_binance_runtime(runtime: BinanceRuntime) -> None:
    await runtime.websocket.stop()
