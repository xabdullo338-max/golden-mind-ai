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
    side: str | None = None
    last_fill_quantity: float | None = None
    last_fill_price: float | None = None
    original_quantity: float | None = None

    @property
    def remaining_quantity(self) -> float | None:
        if self.original_quantity is None:
            return None
        return max(0.0, self.original_quantity - self.executed_quantity)

    def __post_init__(self):
        if self.executed_quantity < 0:
            raise ValueError("executed_quantity cannot be negative")
        if self.last_fill_quantity is not None and self.last_fill_quantity < 0:
            raise ValueError("last_fill_quantity cannot be negative")
        if self.last_fill_price is not None and self.last_fill_price <= 0:
            raise ValueError("last_fill_price must be positive")
        if self.original_quantity is not None and self.original_quantity <= 0:
            raise ValueError("original_quantity must be positive")
        if self.original_quantity is not None and self.executed_quantity > self.original_quantity + 1e-10:
            raise ValueError("executed_quantity cannot exceed original_quantity")

class OrderLifecycle:
    """Tracks monotonic broker order state without assuming broker-specific payloads."""
    _terminal = {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED}
    _rank = {
        OrderStatus.UNKNOWN: 0,
        OrderStatus.NEW: 1,
        OrderStatus.PARTIALLY_FILLED: 2,
        OrderStatus.FILLED: 3,
        OrderStatus.CANCELED: 3,
        OrderStatus.REJECTED: 3,
        OrderStatus.EXPIRED: 3,
    }

    def __init__(self):
        self._orders: dict[tuple[str, str, str], OrderUpdate] = {}

    @staticmethod
    def _key(update: OrderUpdate) -> tuple[str, str, str]:
        return (update.broker.upper(), update.account_id, update.client_order_id)

    def apply(self, update: OrderUpdate) -> OrderUpdate:
        key = self._key(update)
        current = self._orders.get(key)
        if current and current.status in self._terminal:
            return current
        if current:
            current_rank = self._rank[current.status]
            incoming_rank = self._rank[update.status]
            # Broker streams can deliver delayed NEW/PARTIALLY_FILLED events
            # after a newer state. Never let an older lifecycle state regress.
            if incoming_rank < current_rank:
                return current
        self._orders[key] = update
        return update

    def get(self, client_order_id: str, account_id: str | None = None,
            broker: str | None = None) -> OrderUpdate | None:
        if account_id is not None and broker is not None:
            return self._orders.get((broker.upper(), account_id, client_order_id))
        matches = [u for k, u in self._orders.items() if k[2] == client_order_id]
        return matches[0] if len(matches) == 1 else None

    def snapshot(self) -> list[OrderUpdate]:
        return list(self._orders.values())

    def recover_open_order(self, update: OrderUpdate) -> OrderUpdate:
        """Hydrate broker truth after restart without creating a new order."""
        if update.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
            raise ValueError("only open broker orders can be recovered")
        return self.apply(update)

    def has(self, client_order_id: str, account_id: str, broker: str) -> bool:
        return self.get(client_order_id, account_id, broker) is not None
