from __future__ import annotations

import asyncio
import os
import time
import uuid
from decimal import Decimal, ROUND_DOWN
from typing import Any

import httpx

from app.account_manager import AccountManager
from app.config import Settings
from app.event_bus import EventBus
from app.execution_gate import ExecutionGate
from app.journal import TradingJournal
from app.kill_switch import KillSwitch
from app.order_models import OrderRequest, OrderSide
from app.order_router import OrderRouter
from app.portfolio_state import PortfolioStateManager
from app.runtime import build_binance_runtime, start_binance_runtime, stop_binance_runtime


BASE_URL = os.getenv("BINANCE_BASE_URL", "https://testnet.binance.vision").rstrip("/")
API_KEY = os.environ["BINANCE_API_KEY"]
API_SECRET = os.environ["BINANCE_API_SECRET"]
SYMBOL = os.getenv("BINANCE_TEST_SYMBOL", "BTCUSDT").upper()
QUOTE_USDT = Decimal(os.getenv("BINANCE_TEST_QUOTE_USDT", "10"))
TIMEOUT = 15.0


async def rest(client: httpx.AsyncClient, method: str, path: str, *,
               signed: bool = False, params: dict[str, Any] | None = None):
    """Read-only helper for TESTNET market/account metadata.

    Actual orders are deliberately routed through Golden Mind AI's OrderRouter.
    """
    from app.brokers.binance import BinanceAdapter

    adapter = BinanceAdapter(
        account_id="SMOKE-READONLY",
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_url=BASE_URL,
        mode="TESTNET",
    )
    return await adapter._request(method, path, signed=signed, params=params)


def step_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


async def wait_lifecycle(runtime, client_order_id: str, timeout: float = 20.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        update = runtime.coordinator.lifecycle.get(
            client_order_id,
            account_id=runtime.account_id,
            broker="BINANCE",
        )
        if update is not None:
            return update
        await asyncio.sleep(0.1)
    raise RuntimeError(f"No Golden Mind execution lifecycle update for {client_order_id}")


async def main():
    if "testnet.binance.vision" not in BASE_URL:
        raise RuntimeError("REFUSING TO RUN: BINANCE_BASE_URL is not Binance TESTNET")
    if not API_KEY.strip() or not API_SECRET.strip():
        raise RuntimeError("BINANCE_API_KEY and BINANCE_API_SECRET are required")

    settings = Settings(
        app_env="ci",
        trading_mode="TESTNET",
        auto_register_accounts=True,
        binance_account_id="BINANCE-TEST-SMOKE",
        binance_api_key=API_KEY,
        binance_api_secret=API_SECRET,
        binance_base_url=BASE_URL,
        allowed_symbols=SYMBOL,
    )

    accounts = AccountManager()
    portfolio_state = PortfolioStateManager()
    event_bus = EventBus()
    journal = TradingJournal("data/golden_mind_ai_smoke.db")

    runtime = build_binance_runtime(
        settings, accounts, portfolio_state, event_bus, journal
    )
    router = OrderRouter(
        accounts,
        kill_switch=KillSwitch(),
        execution_gate=ExecutionGate(),
        portfolio_state=portfolio_state,
    )

    try:
        await start_binance_runtime(runtime)
        if not portfolio_state.is_confirmed(runtime.account_id):
            raise RuntimeError("Golden Mind AI TESTNET runtime was not reconciled/confirmed")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            info = await rest(
                client, "GET", "/api/v3/exchangeInfo",
                params={"symbol": SYMBOL},
            )
            ticker = await rest(
                client, "GET", "/api/v3/ticker/price",
                params={"symbol": SYMBOL},
            )

            symbol_info = info["symbols"][0]
            filters = {item["filterType"]: item for item in symbol_info["filters"]}
            lot = filters["LOT_SIZE"]
            step = Decimal(lot["stepSize"])
            min_qty = Decimal(lot["minQty"])
            min_notional = Decimal(
                filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
                .get("minNotional", "0")
            )
            price = Decimal(str(ticker["price"]))
            quantity = step_down(QUOTE_USDT / price, step)

            if quantity < min_qty:
                raise RuntimeError(f"Calculated quantity {quantity} is below minQty {min_qty}")
            if quantity * price < min_notional:
                raise RuntimeError(
                    f"Calculated notional {quantity * price} is below minNotional {min_notional}"
                )

            client_id = f"GMAI-SMOKE-{uuid.uuid4().hex[:16]}"
            buy = await router.route(
                runtime.account_id,
                OrderRequest(
                    client_order_id=client_id,
                    symbol=SYMBOL,
                    side=OrderSide.BUY,
                    quantity=float(quantity),
                ),
            )
            buy_update = await wait_lifecycle(runtime, client_id)

            if buy.get("status") != "FILLED" or buy_update.status.value != "FILLED":
                raise RuntimeError(
                    f"BUY was not fully executed: REST={buy} "
                    f"GMAI={buy_update}"
                )

            executed_qty = Decimal(str(buy.get("executedQty", "0")))
            if executed_qty <= 0:
                raise RuntimeError("BUY executedQty is zero")

            sell_qty = step_down(executed_qty, step)
            sell_id = f"GMAI-SMOKE-SELL-{uuid.uuid4().hex[:12]}"
            sell = await router.route(
                runtime.account_id,
                OrderRequest(
                    client_order_id=sell_id,
                    symbol=SYMBOL,
                    side=OrderSide.SELL,
                    quantity=float(sell_qty),
                ),
            )
            sell_update = await wait_lifecycle(runtime, sell_id)

            if sell.get("status") != "FILLED" or sell_update.status.value != "FILLED":
                raise RuntimeError(
                    f"SELL was not fully executed: REST={sell} "
                    f"GMAI={sell_update}"
                )

            account_after = await rest(
                client, "GET", "/api/v3/account", signed=True
            )

        internal_positions = runtime.coordinator.positions.snapshot(runtime.account_id)
        if internal_positions:
            raise RuntimeError(f"Position was not fully closed internally: {internal_positions}")

        print("GMAI TESTNET END-TO-END: PASS")
        print(f"symbol={SYMBOL}")
        print(f"buy_order_id={buy.get('orderId')} executedQty={buy.get('executedQty')}")
        print(f"buy_gmai_status={buy_update.status.value} avgPrice={buy_update.average_price}")
        print(f"sell_order_id={sell.get('orderId')} executedQty={sell.get('executedQty')}")
        print(f"sell_gmai_status={sell_update.status.value} avgPrice={sell_update.average_price}")
        print(f"portfolio_confirmed={portfolio_state.is_confirmed(runtime.account_id)}")
        print("Binance REST order -> Golden Mind router -> Binance WebSocket -> lifecycle -> position engine: VERIFIED")
        print(f"post_trade_account_assets={len(account_after.get('balances', []))}")
    finally:
        await stop_binance_runtime(runtime)


if __name__ == "__main__":
    asyncio.run(main())
