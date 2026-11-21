from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .account_manager import AccountManager
from .idempotency import OrderIdempotencyGuard
from .kill_switch import KillSwitch
from .order_models import OrderRequest
from .execution_gate import ExecutionGate
from .portfolio_state import PortfolioStateManager
from .portfolio import AccountSnapshot, DailyLossGuard
from .order_lifecycle import OrderLifecycle
from .risk_engine import RiskEngine
from .risk_snapshot import RiskSnapshotProvider
from .market_data import MarketTick
from .market_data_store import MarketDataStore


class OrderRouter:
    def __init__(
        self,
        accounts: AccountManager,
        kill_switch: KillSwitch | None = None,
        idempotency: OrderIdempotencyGuard | None = None,
        execution_gate: ExecutionGate | None = None,
        portfolio_state: PortfolioStateManager | None = None,
        daily_loss_guard: DailyLossGuard | None = None,
        snapshot_provider: Callable[[str], AccountSnapshot | None] | None = None,
        lifecycle: OrderLifecycle | None = None,
        risk_engine: RiskEngine | None = None,
        risk_snapshot_provider: RiskSnapshotProvider | None = None,
        market_tick_provider: Callable[[str, str], Awaitable[Any | None]] | None = None,
        market_data_store: MarketDataStore | None = None,
    ):
        self.accounts = accounts
        self.kill_switch = kill_switch or KillSwitch()
        self.idempotency = idempotency or OrderIdempotencyGuard()
        self.execution_gate = execution_gate
        self.portfolio_state = portfolio_state
        self.daily_loss_guard = daily_loss_guard or DailyLossGuard()
        self.snapshot_provider = snapshot_provider
        self.lifecycle = lifecycle
        self.risk_engine = risk_engine
        self.risk_snapshot_provider = risk_snapshot_provider
        self.market_tick_provider = market_tick_provider
        self.market_data_store = market_data_store

    def _daily_loss_ok(self, account_id: str, *, live: bool) -> bool:
        # Simulated/testnet execution can proceed without a live account
        # snapshot. LIVE execution must have an actual risk snapshot.
        if not live:
            return True
        if self.snapshot_provider is None:
            return False
        snapshot = self.snapshot_provider(account_id)
        return snapshot is not None and self.daily_loss_guard.allowed(snapshot)

    async def _fresh_market_tick(self, account_id: str, symbol: str) -> MarketTick | None:
        """Read cached market data first; the broker provider is acquisition only.

        Once a tick is acquired it is stored and every risk decision uses the
        store as the source of truth. Stale or missing data never gets silently
        substituted with an older quote.
        """
        broker = "BINANCE"
        max_age = (
            self.risk_engine.max_market_data_age_seconds
            if self.risk_engine is not None
            else 2.0
        )

        if self.market_data_store is not None:
            cached = self.market_data_store.get(broker, symbol)
            if cached is not None:
                age = self.market_data_store.age_seconds(broker, symbol)
                if age is not None and age <= max_age:
                    return cached

        if self.market_tick_provider is None:
            if self.market_data_store is not None:
                return self.market_data_store.require_fresh(
                    broker, symbol, max_age
                )
            return None

        tick = await self.market_tick_provider(account_id, symbol)
        if tick is None:
            if self.market_data_store is not None:
                return self.market_data_store.require_fresh(
                    broker, symbol, max_age
                )
            return None

        if self.market_data_store is not None:
            self.market_data_store.update(tick)
            return self.market_data_store.require_fresh(
                broker, symbol, max_age
            )
        return tick

    async def route(self, account_id: str, order: OrderRequest) -> dict[str, Any]:
        self.kill_switch.assert_allowed(account_id)
        managed = self.accounts.accounts.get(account_id)
        if managed is None:
            raise RuntimeError(f"Unknown account {account_id}")

        if self.execution_gate is not None:
            confirmed = (
                self.portfolio_state.is_confirmed(account_id)
                if self.portfolio_state is not None
                else False
            )
            live = managed.adapter.account.mode == "LIVE"
            self.execution_gate.assert_ready(
                account_enabled=managed.enabled,
                state_confirmed=confirmed,
                daily_loss_ok=self._daily_loss_ok(account_id, live=live),
                # LIVE remains explicitly disabled until a separate,
                # authenticated live-trading enablement mechanism is added.
                live_enabled=not live,
            )

        if self.risk_engine is not None:
            metadata = order.metadata or {}
            tick = await self._fresh_market_tick(account_id, order.symbol)

            current_price = metadata.get("current_price") or metadata.get("price")
            spread_pct = metadata.get("spread_pct")
            market_age = metadata.get("market_data_age_seconds")

            if tick is not None:
                current_price = tick.price
                spread_pct = tick.spread_pct
                timestamp = tick.timestamp
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                market_age = max(
                    0.0,
                    (datetime.now(timezone.utc) - timestamp).total_seconds(),
                )

            snapshot = None
            total_exposure = 0.0
            symbol_exposure = 0.0
            managed_state = (
                self.portfolio_state.get(account_id)
                if self.portfolio_state is not None
                else None
            )

            if (
                self.risk_snapshot_provider is not None
                and managed_state is not None
                and current_price is not None
            ):
                prices = {order.symbol.upper(): float(current_price)}
                for asset, quantity in managed_state.positions.items():
                    if float(quantity) <= 0:
                        continue
                    symbol = str(asset).upper()
                    if not symbol.endswith("USDT"):
                        symbol = f"{symbol}USDT"
                    if symbol not in prices:
                        position_tick = await self._fresh_market_tick(
                            account_id, symbol
                        )
                        if position_tick is None:
                            raise RuntimeError(
                                f"market data unavailable for {symbol}"
                            )
                        prices[symbol] = position_tick.price

                total_exposure, exposures = self.risk_snapshot_provider.exposures(
                    managed_state, prices=prices
                )
                symbol_exposure = exposures.get(order.symbol.upper(), 0.0)
                snapshot = self.risk_snapshot_provider.build(
                    managed_state, prices=prices
                )

            if snapshot is None:
                raise RuntimeError("risk snapshot is unavailable")

            self.risk_engine.assert_allowed(
                order,
                snapshot,
                current_price=current_price,
                stop_price=metadata.get("stop_price"),
                spread_pct=spread_pct,
                expected_fill_price=metadata.get("expected_fill_price"),
                market_data_age_seconds=market_age,
                current_total_exposure=total_exposure,
                current_symbol_exposure=symbol_exposure,
            )

        key = f"{account_id}:{order.client_order_id}"
        # After a restart, broker recovery may already have hydrated this client
        # order into the lifecycle. Never submit it again just because the
        # in-memory idempotency window was lost.
        if self.lifecycle is not None:
            recovered = self.lifecycle.get(
                order.client_order_id,
                account_id,
                managed.adapter.account.broker,
            )
            if recovered is not None:
                raise RuntimeError(
                    "duplicate client order id: order already known to lifecycle"
                )
        decision = self.idempotency.check_and_mark(key)
        if not decision.allowed:
            raise RuntimeError(decision.reason)

        try:
            return await self.accounts.order_to(account_id, order)
        except Exception:
            self.idempotency.forget(key)
            raise

    async def broadcast(self, order: OrderRequest) -> list[dict[str, Any]]:
        accounts = [a for a in self.accounts.list_accounts() if a["enabled"]]
        for account in accounts:
            self.kill_switch.assert_allowed(account["account_id"])
        tasks = [self.route(a["account_id"], order) for a in accounts]
        return await asyncio.gather(*tasks) if tasks else []
