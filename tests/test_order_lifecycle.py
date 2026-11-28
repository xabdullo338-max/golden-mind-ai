from app.order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate


def u(status, qty=0, original=None, last_fill_qty=None, last_fill_price=None):
    return OrderUpdate(
        "BINANCE",
        "A",
        "cid-1",
        status,
        "BTCUSDT",
        qty,
        average_price=50000.0 if qty else None,
        last_fill_quantity=last_fill_qty,
        last_fill_price=last_fill_price,
        original_quantity=original,
    )


def test_lifecycle_accepts_partial_then_fill():
    x = OrderLifecycle()
    x.apply(u(OrderStatus.PARTIALLY_FILLED, 0.1, original=0.2))
    x.apply(u(OrderStatus.FILLED, 0.2, original=0.2))
    assert x.get("cid-1").status == OrderStatus.FILLED
    assert x.get("cid-1").executed_quantity == 0.2


def test_terminal_state_is_not_regressed():
    x = OrderLifecycle()
    x.apply(u(OrderStatus.FILLED, 1, original=1))
    x.apply(u(OrderStatus.NEW, 0, original=1))
    x.apply(u(OrderStatus.PARTIALLY_FILLED, 0.5, original=1))
    assert x.get("cid-1").status == OrderStatus.FILLED


def test_unknown_after_partial_does_not_regress_state():
    x = OrderLifecycle()
    x.apply(u(OrderStatus.PARTIALLY_FILLED, 0.1, original=0.2))
    x.apply(u(OrderStatus.UNKNOWN, 0, original=0.2))
    assert x.get("cid-1").status == OrderStatus.PARTIALLY_FILLED
    assert x.get("cid-1").executed_quantity == 0.1


def test_canceled_is_terminal_and_immutable():
    x = OrderLifecycle()
    canceled = u(OrderStatus.CANCELED, 0.1, original=0.2)
    x.apply(canceled)
    x.apply(u(OrderStatus.FILLED, 0.2, original=0.2))
    x.apply(u(OrderStatus.PARTIALLY_FILLED, 0.15, original=0.2))
    assert x.get("cid-1") == canceled


def test_duplicate_update_is_idempotent():
    x = OrderLifecycle()
    update = u(
        OrderStatus.PARTIALLY_FILLED,
        0.1,
        original=0.2,
        last_fill_qty=0.1,
        last_fill_price=50000.0,
    )
    assert x.apply(update) == update
    assert x.apply(update) == update
    assert x.snapshot() == [update]


def test_remaining_quantity_is_never_negative():
    update = u(OrderStatus.FILLED, 0.2, original=0.2)
    assert update.remaining_quantity == 0.0


def test_different_accounts_do_not_collide_on_client_order_id():
    x = OrderLifecycle()
    first = OrderUpdate("BINANCE", "A", "same-id", OrderStatus.FILLED, "BTCUSDT", 1, original_quantity=1)
    second = OrderUpdate("BINANCE", "B", "same-id", OrderStatus.NEW, "ETHUSDT", 0, original_quantity=1)
    x.apply(first)
    x.apply(second)
    assert x.get("same-id", "A", "BINANCE").status == OrderStatus.FILLED
    assert x.get("same-id", "B", "BINANCE").status == OrderStatus.NEW
