import pytest

from app.account_manager import AccountManager
from app.config import Settings
from app.event_bus import EventBus
from app.journal import TradingJournal
from app.portfolio_state import PortfolioStateManager
from app.runtime import _ws_url, build_binance_runtime, start_binance_runtime


def test_binance_testnet_uses_testnet_websocket():
    assert _ws_url("https://testnet.binance.vision") == (
        "wss://ws-api.testnet.binance.vision/ws-api/v3"
    )


def test_binance_live_uses_production_websocket():
    assert _ws_url("https://api.binance.com") == (
        "wss://ws-api.binance.com:443/ws-api/v3"
    )


@pytest.mark.asyncio
async def test_paper_runtime_bootstraps_and_reconciles(tmp_path):
    settings = Settings(
        trading_mode="PAPER",
        initial_balance_usdt=300,
        auto_register_accounts=True,
    )
    accounts = AccountManager()
    state = PortfolioStateManager()
    bus = EventBus()
    journal = TradingJournal(str(tmp_path / "journal.db"))

    runtime = build_binance_runtime(settings, accounts, state, bus, journal)
    await start_binance_runtime(runtime)

    assert accounts.list_accounts()[0]["account_id"] == "BINANCE-01"
    assert state.is_confirmed("BINANCE-01") is True
    assert state.get("BINANCE-01").balances["USDT"] == 300.0


@pytest.mark.asyncio
async def test_testnet_without_credentials_stays_unconfirmed(tmp_path):
    settings = Settings(
        trading_mode="TESTNET",
        binance_api_key="",
        binance_api_secret="",
    )
    accounts = AccountManager()
    state = PortfolioStateManager()
    bus = EventBus()
    journal = TradingJournal(str(tmp_path / "journal.db"))

    runtime = build_binance_runtime(settings, accounts, state, bus, journal)
    await start_binance_runtime(runtime)

    assert state.is_confirmed("BINANCE-01") is False
