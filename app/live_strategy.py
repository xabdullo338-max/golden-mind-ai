from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from .account_manager import AccountManager
from .brokers.binance import BinanceAdapter
from .config import Settings
from .market_data_store import MarketDataStore
from .order_models import OrderRequest, OrderSide
from .order_router import OrderRouter
from .portfolio_state import PortfolioStateManager
from .risk_engine import RiskEngine
from .strategy_engine import AdaptiveEnsembleStrategy, Candle, Signal

log = logging.getLogger(__name__)


@dataclass
class LiveStrategyRunner:
    """Conservative 1-minute Binance Spot strategy runner.

    It is deliberately disabled unless Settings.live_trading_enabled is true
    and the Binance account itself is configured as LIVE.
    """

    settings: Settings
    accounts: AccountManager
    router: OrderRouter
    portfolio_state: PortfolioStateManager
    risk_engine: RiskEngine
    market_data: MarketDataStore
    strategy: AdaptiveEnsembleStrategy
    last_candles: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.last_candles is None:
            self.last_candles = {}

    async def run_forever(self) -> None:
        account_id = self.settings.binance_account_id
        managed = self.accounts.accounts.get(account_id)
        if managed is None or managed.adapter.account.mode != "LIVE":
            raise RuntimeError("live strategy requires a LIVE Binance account")
        if not self.settings.live_trading_enabled:
            raise RuntimeError("live strategy is disabled")

        adapter = managed.adapter
        if not isinstance(adapter, BinanceAdapter):
            raise RuntimeError("live strategy requires BinanceAdapter")

        while True:
            try:
                await self.step(adapter, account_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("live strategy iteration failed")
            await asyncio.sleep(15)

    async def step(self, adapter: BinanceAdapter, account_id: str) -> None:
        for symbol in sorted(self.settings.symbols):
            rows = await adapter.get_candles(symbol, "1m", 60)
            if len(rows) < 46:
                continue

            # Evaluate the last fully closed 1m candle. The newest Binance
            # candle can still be forming and must not drive an order.
            closed_rows = rows[:-1]
            candle_timestamp = int(closed_rows[-1]["timestamp"])
            if self.last_candles.get(symbol) == candle_timestamp:
                continue

            # If a previous broker request timed out, its outcome is unknown.
            # Do not create a new order until reconciliation resolves it.
            if self.router.pending_orders is not None:
                pending = self.router.pending_orders.list_account(
                    account_id,
                    managed.adapter.account.broker,
                )
                if any(item.symbol.upper() == symbol.upper() for item in pending):
                    continue

            candles = [Candle(**row) for row in closed_rows]
            decision = self.strategy.evaluate(candles)
            tick = await adapter.get_market_tick(symbol)
            if tick is None:
                continue

            state = self.portfolio_state.get(account_id)
            if state is None or not state.confirmed:
                continue

            base = symbol.removesuffix("USDT")
            held = float(state.positions.get(base, 0.0))
            if held <= 0:
                held = float(state.positions.get(symbol, 0.0))

            if decision.signal == Signal.HOLD:
                self.last_candles[symbol] = candle_timestamp
                continue

            if decision.signal == Signal.BUY and held <= 1e-12:
                balance = float(state.balances.get("USDT", 0.0))
                if balance <= 0:
                    continue
                stop = decision.stop_price
                if stop is None:
                    continue
                quantity = self.risk_engine.position_size(
                    equity=balance,
                    entry_price=tick.price,
                    stop_price=stop,
                    risk_pct=self.risk_engine.max_risk_per_trade_pct,
                    max_notional_pct=(
                        self.settings.live_max_order_notional_usdt / balance * 100
                    ),
                )
                if quantity <= 0:
                    continue
                order = OrderRequest(
                    client_order_id=f"GMAI-{symbol}-{int(datetime.now(timezone.utc).timestamp()*1000)}",
                    symbol=symbol,
                    side=OrderSide.BUY,
                    quantity=quantity,
                    metadata={
                        "current_price": tick.price,
                        "stop_price": stop,
                        "take_profit_price": decision.take_profit_price,
                        "strategy": "adaptive_ensemble_1m",
                        "regime": decision.regime.value,
                        "model_score": decision.model_score,
                        "ai_probability": decision.ai_probability,
                        "confidence": decision.confidence,
                    },
                )
                await self.router.route(account_id, order)
                self.last_candles[symbol] = candle_timestamp

            elif decision.signal == Signal.SELL and held > 1e-12:
                quantity = min(held, self.settings.live_max_order_notional_usdt / tick.price)
                if quantity <= 0:
                    continue
                order = OrderRequest(
                    client_order_id=f"GMAI-{symbol}-SELL-{int(datetime.now(timezone.utc).timestamp()*1000)}",
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=quantity,
                    metadata={
                        "current_price": tick.price,
                        "strategy": "adaptive_ensemble_1m_exit",
                        "regime": decision.regime.value,
                        "model_score": decision.model_score,
                        "confidence": decision.confidence,
                    },
                )
                await self.router.route(account_id, order)
