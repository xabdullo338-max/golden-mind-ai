from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BrokerState:
    account_id: str
    broker: str
    balances: dict[str, float]
    positions: dict[str, float]
    open_orders: list[dict[str, Any]]
    executions: list[dict[str, Any]]
    confirmed: bool = True


class PortfolioStateManager:
    """Broker-authoritative state boundary used after startup/reconnect."""

    def __init__(self):
        self._states: dict[str, BrokerState] = {}

    def mark_unconfirmed(self, account_id: str, broker: str) -> None:
        current = self._states.get(account_id)
        self._states[account_id] = BrokerState(
            account_id,
            broker,
            current.balances if current else {},
            current.positions if current else {},
            current.open_orders if current else [],
            current.executions if current else [],
            False,
        )

    def reconcile(
        self,
        account_id: str,
        broker: str,
        balances: dict[str, float],
        positions: list[dict[str, Any]],
        open_orders: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> BrokerState:
        normalized_positions = {
            str(p["asset"]).upper(): float(p["quantity"]) for p in positions
        }
        normalized_balances = {
            str(asset).upper(): float(quantity)
            for asset, quantity in balances.items()
            if float(quantity) != 0
        }
        state = BrokerState(
            account_id,
            broker,
            normalized_balances,
            normalized_positions,
            list(open_orders),
            list(executions),
            True,
        )
        self._states[account_id] = state
        return state

    def is_confirmed(self, account_id: str) -> bool:
        state = self._states.get(account_id)
        return bool(state and state.confirmed)

    def get(self, account_id: str) -> BrokerState | None:
        return self._states.get(account_id)
