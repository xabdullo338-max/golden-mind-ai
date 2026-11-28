import pytest

from app.order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate


def update(status, qty, client="o-1"):
    return OrderUpdate(
        broker="BINANCE",
        account_id="A",
        client_order_id=client,
        status=status,
        symbol="BTCUSDT",
        executed_quantity=qty,
        average_price=100.0 if qty else None,
        broker_order_id="42",
        side="BUY",
    )


def test_lifecycle_rejects_delayed_new_after_partial_fill():
    lifecycle = OrderLifecycle()

    assert lifecycle.apply(update(OrderStatus.NEW, 0)).status == OrderStatus.NEW
    assert lifecycle.apply(update(OrderStatus.PARTIALLY_FILLED, 0.4)).status == OrderStatus.PARTIALLY_FILLED

    applied = lifecycle.apply(update(OrderStatus.NEW, 0))
    assert applied.status == OrderStatus.PARTIALLY_FILLED
    assert applied.executed_quantity == 0.4


def test_lifecycle_keeps_terminal_state_against_stale_events():
    lifecycle = OrderLifecycle()

    assert lifecycle.apply(update(OrderStatus.FILLED, 1.0)).status == OrderStatus.FILLED

    applied = lifecycle.apply(update(OrderStatus.PARTIALLY_FILLED, 0.5))
    assert applied.status == OrderStatus.FILLED
    assert applied.executed_quantity == 1.0


def test_lifecycle_allows_partial_to_filled():
    lifecycle = OrderLifecycle()

    lifecycle.apply(update(OrderStatus.PARTIALLY_FILLED, 0.5))
    applied = lifecycle.apply(update(OrderStatus.FILLED, 1.0))

    assert applied.status == OrderStatus.FILLED
    assert applied.executed_quantity == 1.0


def test_lifecycle_rejects_stale_partial_after_filled():
    lifecycle = OrderLifecycle()

    lifecycle.apply(update(OrderStatus.PARTIALLY_FILLED, 0.6))
    assert lifecycle.apply(update(OrderStatus.FILLED, 1.0)).status == OrderStatus.FILLED

    applied = lifecycle.apply(update(OrderStatus.PARTIALLY_FILLED, 0.8))
    assert applied.status == OrderStatus.FILLED
    assert applied.executed_quantity == 1.0


def test_lifecycle_rejects_stale_partial_after_canceled():
    lifecycle = OrderLifecycle()

    lifecycle.apply(update(OrderStatus.PARTIALLY_FILLED, 0.4))
    assert lifecycle.apply(update(OrderStatus.CANCELED, 0.4)).status == OrderStatus.CANCELED

    applied = lifecycle.apply(update(OrderStatus.PARTIALLY_FILLED, 0.4))
    assert applied.status == OrderStatus.CANCELED
    assert applied.executed_quantity == 0.4
