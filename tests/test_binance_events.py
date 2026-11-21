from app.binance_events import execution_report_to_update
from app.order_lifecycle import OrderStatus


def test_execution_report_maps_cumulative_fill():
    update = execution_report_to_update({
        "e": "executionReport", "s": "BTCUSDT", "c": "gmai-1",
        "X": "PARTIALLY_FILLED", "z": "0.25", "Z": "25000", "i": 123
    }, "BINANCE-01")
    assert update is not None
    assert update.status is OrderStatus.PARTIALLY_FILLED
    assert update.executed_quantity == 0.25
    # Binance Z is cumulative quote quantity and z is cumulative base quantity.
    assert update.average_price == 100000.0
    assert update.broker_order_id == "123"


def test_non_execution_event_is_ignored():
    assert execution_report_to_update({"e": "outboundAccountPosition"}, "BINANCE-01") is None
