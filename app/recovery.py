from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .position_engine import PositionEngine
from .order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate
from .pending_orders import PendingOrderStore


class RecoveryPhase(str, Enum):
    IDLE = "IDLE"
    RECONCILING = "RECONCILING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


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

    def __init__(self, accounts, portfolio_state, journal, positions: PositionEngine | None = None,
                 lifecycle: OrderLifecycle | None = None,
                 pending_orders: PendingOrderStore | None = None):
        self.accounts = accounts
        self.portfolio_state = portfolio_state
        self.journal = journal
        self.positions = positions
        self.lifecycle = lifecycle
        self._phase: dict[str, RecoveryPhase] = {}
        self.pending_orders = pending_orders

    def phase(self, account_id: str) -> RecoveryPhase:
        return self._phase.get(account_id, RecoveryPhase.IDLE)

    async def recover_account(self, account_id: str) -> RecoveryResult:
        managed = self.accounts.accounts.get(account_id)
        if not managed or not managed.enabled:
            self._phase[account_id] = RecoveryPhase.FAILED
            return RecoveryResult(account_id, {}, [], [], False, "account unavailable")

        adapter = managed.adapter
        self._phase[account_id] = RecoveryPhase.RECONCILING
        try:
            balances = await adapter.get_balance()
            positions = await adapter.get_positions()
            open_orders = await adapter.get_open_orders()

            if self.positions is not None:
                await self._hydrate_positions(adapter, positions)
            if self.lifecycle is not None:
                self._hydrate_open_orders(
                    adapter.account.account_id,
                    adapter.account.broker,
                    open_orders,
                )
            if self.pending_orders is not None:
                await self._reconcile_pending_orders(
                    adapter.account.account_id,
                    adapter,
                )

            self.portfolio_state.reconcile(
                account_id=account_id,
                broker=adapter.account.broker,
                balances=balances,
                positions=positions,
                open_orders=open_orders,
                executions=[],
            )
            self._phase[account_id] = RecoveryPhase.CONFIRMED
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
            self._phase[account_id] = RecoveryPhase.FAILED
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

        if reconstructed and len(reconstructed) == len(expected_symbols):
            self.positions.clear_account(adapter.account.account_id)
            for symbol, (qty, avg, realized) in reconstructed.items():
                self.positions.hydrate(adapter.account.account_id, symbol, qty, avg, realized)
        elif not expected_symbols:
            self.positions.clear_account(adapter.account.account_id)

    def _hydrate_open_orders(self, account_id: str, broker: str, open_orders: list[dict[str, Any]]) -> None:
        for order in open_orders:
            client_order_id = str(order.get("clientOrderId") or "").strip()
            symbol = str(order.get("symbol") or "").upper().strip()
            side = str(order.get("side") or "").upper().strip()
            status_name = str(order.get("status") or "NEW").upper().strip()
            if not client_order_id or not symbol or side not in {"BUY", "SELL"}:
                continue
            try:
                status = OrderStatus(status_name)
            except ValueError:
                status = OrderStatus.UNKNOWN
            if status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
                continue
            executed = float(order.get("executedQty", order.get("executed_quantity", 0.0)) or 0.0)
            original = float(order.get("origQty", order.get("original_quantity", 0.0)) or 0.0)
            if original <= 0 or executed < 0 or executed > original + 1e-10:
                continue
            avg = order.get("price")
            avg_price = float(avg) if avg not in (None, "", 0, "0") else None
            broker_order_id = order.get("orderId", order.get("broker_order_id"))
            update = OrderUpdate(
                broker=broker,
                account_id=account_id,
                client_order_id=client_order_id,
                status=status,
                symbol=symbol,
                executed_quantity=executed,
                average_price=avg_price,
                broker_order_id=str(broker_order_id) if broker_order_id is not None else None,
                side=side,
                original_quantity=original,
            )
            self.lifecycle.recover_open_order(update)

    async def _reconcile_pending_orders(self, account_id: str, adapter) -> None:
        if self.pending_orders is None or self.lifecycle is None:
            return
        pending = self.pending_orders.list_account(account_id, adapter.account.broker)
        for item in pending:
            broker_order = await adapter.get_order_by_client_id(
                item.symbol, item.client_order_id
            )
            if not broker_order:
                # Do not delete the pending record when the broker cannot
                # prove an outcome. The next recovery attempt must retry lookup.
                continue

            status_name = str(broker_order.get("status") or "UNKNOWN").upper()
            try:
                status = OrderStatus(status_name)
            except ValueError:
                status = OrderStatus.UNKNOWN

            if status is OrderStatus.UNKNOWN:
                continue

            executed = float(
                broker_order.get("executedQty", broker_order.get("executed_quantity", 0.0))
                or 0.0
            )
            original = float(
                broker_order.get("origQty", broker_order.get("original_quantity", item.quantity))
                or item.quantity
            )
            price = broker_order.get("avgPrice", broker_order.get("average_price"))
            avg_price = float(price) if price not in (None, "", 0, "0") else None

            update = OrderUpdate(
                broker=adapter.account.broker,
                account_id=account_id,
                client_order_id=item.client_order_id,
                status=status,
                symbol=item.symbol,
                executed_quantity=executed,
                average_price=avg_price,
                broker_order_id=str(
                    broker_order.get("orderId", broker_order.get("broker_order_id"))
                ),
                side=item.side,
                original_quantity=original,
            )
            self.lifecycle.apply(update)
            if status in {
                OrderStatus.FILLED,
                OrderStatus.CANCELED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED,
            }:
                self.pending_orders.resolve(
                    account_id, item.client_order_id, adapter.account.broker
                )

    async def recover_all(self) -> list[RecoveryResult]:
        return [await self.recover_account(account_id) for account_id in self.accounts.accounts]
