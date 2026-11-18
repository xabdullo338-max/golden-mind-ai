from app.order_lifecycle import OrderLifecycle, OrderStatus, OrderUpdate

def u(status, qty=0):
    return OrderUpdate("BINANCE", "A", "cid-1", status, "BTCUSDT", qty)

def test_lifecycle_accepts_partial_then_fill():
    x = OrderLifecycle()
    x.apply(u(OrderStatus.PARTIALLY_FILLED, 0.1))
    x.apply(u(OrderStatus.FILLED, 0.2))
    assert x.get("cid-1").status == OrderStatus.FILLED
    assert x.get("cid-1").executed_quantity == 0.2

def test_terminal_state_is_not_regressed():
    x = OrderLifecycle()
    x.apply(u(OrderStatus.FILLED, 1))
    x.apply(u(OrderStatus.NEW, 0))
    assert x.get("cid-1").status == OrderStatus.FILLED