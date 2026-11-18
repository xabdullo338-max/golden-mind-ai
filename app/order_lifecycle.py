from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class OrderUpdate:
    broker: str
    account_id: str
    client_order_id: str
    status: OrderStatus
    symbol: str
    executed_quantity: float = 0.0
    average_price: float | None = None
    broker_order_id: str | None = None

    def __post_init__(self):
        if self.executed_quantity < 0:
            raise ValueError("executed_quantity cannot be negative")

class OrderLifecycle:
    """Tracks monotonic broker order state without assuming broker-specific payloads."""
    _terminal = {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED}

    def __init__(self):
        self._orders: dict[str, OrderUpdate] = {}

    def apply(self, update: OrderUpdate) -> OrderUpdate:
        current = self._orders.get(update.client_order_id)
        if current and current.status in self._terminal:
            return current
        self._orders[update.client_order_id] = update
        return update

    def get(self, client_order_id: str) -> OrderUpdate | None:
        return self._orders.get(client_order_id)

    def snapshot(self) -> list[OrderUpdate]:
        return list(self._orders.values())
