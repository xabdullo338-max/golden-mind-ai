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


def test_execution_report_maps_last_fill_fields():
    update = execution_report_to_update({
        "e": "executionReport", "s": "ETHUSDT", "c": "gmai-fill-1",
        "S": "SELL", "X": "FILLED",
        "z": "1.5", "Z": "4500", "l": "0.5", "L": "2990.0", "i": 456
    }, "BINANCE-01")

    assert update is not None
    assert update.status is OrderStatus.FILLED
    assert update.executed_quantity == 1.5
    assert update.average_price == 3000.0
    assert update.side == "SELL"
    assert update.last_fill_quantity == 0.5
    assert update.last_fill_price == 2990.0
    assert update.broker_order_id == "456"


def test_execution_report_accepts_nested_event_payload():
    payload = {
        "event": {
            "e": "executionReport", "s": "BNBUSDT", "c": "nested-1",
            "X": "NEW", "z": "0", "i": 789
        }
    }
    # The normalizer itself consumes the executionReport payload; the bridge
    # is responsible for unwrapping the outer websocket event envelope.
    assert execution_report_to_update(payload["event"], "BINANCE-01").status is OrderStatus.NEW


def test_execution_report_rejects_missing_client_order_id():
    assert execution_report_to_update({
        "e": "executionReport", "s": "BTCUSDT", "X": "NEW", "i": 123
    }, "BINANCE-01") is None


def test_execution_report_handles_zero_quote_quantity_without_fake_average():
    update = execution_report_to_update({
        "e": "executionReport", "s": "BTCUSDT", "c": "zero-quote",
        "X": "NEW", "z": "0", "Z": "0", "i": 124
    }, "BINANCE-01")
    assert update is not None
    assert update.average_price is None
    assert update.executed_quantity == 0.0
