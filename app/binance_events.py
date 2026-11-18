from __future__ import annotations

from typing import Any

from .order_lifecycle import OrderStatus, OrderUpdate

_STATUS = {
    "NEW": OrderStatus.NEW,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "CANCELED": OrderStatus.CANCELED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.EXPIRED,
}

def execution_report_to_update(message: dict[str, Any], account_id: str) -> OrderUpdate | None:
    """Normalize Binance Spot executionReport into the broker-neutral order model."""
    if message.get("e") != "executionReport" and message.get("event") != "executionReport":
        return None
    status = _STATUS.get(str(message.get("X", "")).upper(), OrderStatus.UNKNOWN)
    symbol = str(message.get("s", "")).upper()
    client_id = str(message.get("c", ""))
    if not symbol or not client_id:
        return None

    cumulative_qty = float(message.get("z", 0.0) or 0.0)
    avg_price = float(message.get("Z", 0.0) or 0.0)
    if avg_price <= 0:
        avg_price = None

    side = str(message.get("S", "")).upper() or None

    return OrderUpdate(
        broker="BINANCE",
        account_id=account_id,
        client_order_id=client_id,
        status=status,
        symbol=symbol,
        executed_quantity=cumulative_qty,
        average_price=avg_price,
        broker_order_id=str(message.get("i")) if message.get("i") is not None else None,
        side=side,
    )
