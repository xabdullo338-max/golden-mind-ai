from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .position_engine import PositionEngine


@dataclass(frozen=True)
class RecoveryResult:
    account_id: str
    broker_balances: dict[str, float]
    broker_positions: list[dict[str, Any]]
    broker_open_orders: list[dict[str, Any]]
    confirmed: bool
    reason: str = ""


class BrokerRecovery:
    """Rebuild runtime state from broker truth after restart/reconnect."""

    def __init__(self, accounts, portfolio_state, journal, positions: PositionEngine | None = None):
        self.accounts = accounts
        self.portfolio_state = portfolio_state
        self.journal = journal
        self.positions = positions

    async def recover_account(self, account_id: str) -> RecoveryResult:
        managed = self.accounts.accounts.get(account_id)
        if not managed or not managed.enabled:
            return RecoveryResult(account_id, {}, [], [], False, "account unavailable")

        adapter = managed.adapter
        try:
            balances = await adapter.get_balance()
            positions = await adapter.get_positions()
            open_orders = await adapter.get_open_orders()

            # Recover cost basis from broker trade history before hydrating the
            # local position engine. Never invent an entry price when history
            # cannot fully explain the broker-held quantity.
            if self.positions is not None:
                await self._hydrate_positions(adapter, positions)

            self.portfolio_state.reconcile(
                account_id=account_id,
                broker=adapter.account.broker,
                balances=balances,
                positions=positions,
                open_orders=open_orders,
                executions=[],
            )
            return RecoveryResult(
                account_id,
                balances,
                positions,
                open_orders,
                True,
                "broker balances, positions and open orders reconciled",
            )
        except Exception as exc:
            self.portfolio_state.mark_unconfirmed(
                account_id, adapter.account.broker
            )
            return RecoveryResult(
                account_id,
                {},
                [],
                [],
                False,
                f"recovery failed: {type(exc).__name__}",
            )

    async def _hydrate_positions(self, adapter, positions: list[dict[str, Any]]) -> None:
        reconstructed: dict[str, tuple[float, float, float]] = {}
        expected_symbols = {
            str(p.get("asset", "")).upper()
            for p in positions
            if str(p.get("asset", "")).strip() and float(p.get("quantity", 0.0)) > 0
        }
        for position in positions:
            asset = str(position.get("asset", "")).upper()
            broker_qty = float(position.get("quantity", 0.0))
            if not asset or broker_qty <= 0:
                continue

            symbol = f"{asset}USDT"
            trades = await adapter.get_trade_history(symbol, limit=1000)
            qty = 0.0
            cost = 0.0
            realized = 0.0
            complete = True

            for trade in sorted(trades, key=lambda t: (int(t.get("time", 0)), int(t.get("id", 0)))):
                trade_qty = float(trade.get("qty", 0.0))
                price = float(trade.get("price", 0.0))
                if trade_qty <= 0 or price <= 0:
                    continue

                commission = float(trade.get("commission", 0.0) or 0.0)
                commission_asset = str(trade.get("commissionAsset", "")).upper()
                is_buy = bool(trade.get("isBuyer", str(trade.get("side", "")).upper() == "BUY"))

                if is_buy:
                    received_qty = trade_qty - commission if commission_asset == asset else trade_qty
                    qty += received_qty
                    cost += trade_qty * price
                    if commission_asset == "USDT":
                        cost += commission
                else:
                    if trade_qty > qty + 1e-10:
                        complete = False
                        break
                    avg = cost / qty if qty > 0 else 0.0
                    realized += trade_qty * (price - avg)
                    qty -= trade_qty
                    cost -= trade_qty * avg
                    if commission_asset == asset:
                        qty -= commission
                    elif commission_asset == "USDT":
                        realized -= commission

            tolerance = max(1e-8, broker_qty * 1e-6)
            if complete and abs(qty - broker_qty) <= tolerance and qty > 0 and cost >= 0:
                reconstructed[symbol] = (broker_qty, cost / qty, realized)

        # Only replace the local snapshot when broker history fully reconciles.
        # Incomplete history must not fabricate an entry price.
        if reconstructed and len(reconstructed) == len(expected_symbols):
            self.positions.clear_account(adapter.account.account_id)
            for symbol, (qty, avg, realized) in reconstructed.items():
                self.positions.hydrate(adapter.account.account_id, symbol, qty, avg, realized)
        elif not expected_symbols:
            # Broker reports no open base-asset positions, so stale local
            # positions can safely be removed.
            self.positions.clear_account(adapter.account.account_id)

    async def recover_all(self) -> list[RecoveryResult]:
        return [
            await self.recover_account(account_id)
            for account_id in self.accounts.accounts
        ]
