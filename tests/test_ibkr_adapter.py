import pytest
from app.brokers.ibkr import IBKRAdapter

@pytest.mark.asyncio
async def test_ibkr_paper_order_is_local():
    adapter = IBKRAdapter("IBKR-PAPER", mode="PAPER")
    result = await adapter.place_order("AAPL", "BUY", 1)
    assert result["status"] == "FILLED"
    assert result["broker"] == "IBKR"

@pytest.mark.asyncio
async def test_ibkr_execution_requires_session_cookie():
    adapter = IBKRAdapter("IBKR-01", mode="LIVE")
    with pytest.raises(RuntimeError):
        await adapter.place_order("AAPL", "BUY", 1, conid=265598)


@pytest.mark.asyncio
async def test_ibkr_positions_are_normalized(monkeypatch):
    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")

    async def fake_request(method, path, *, json=None):
        assert method == "GET"
        assert path == "/v1/api/portfolio/IBKR-01/positions/0"
        return [
            {"symbol": "AAPL", "position": "2", "avgPrice": "210.50", "conid": 265598},
            {"symbol": "TSLA", "position": 0, "avgPrice": "400"},
            {"symbol": "", "position": 5},
            {"symbol": "MSFT", "position": "bad"},
        ]

    monkeypatch.setattr(adapter, "_request", fake_request)

    positions = await adapter.get_positions()

    assert positions == [{
        "asset": "AAPL",
        "quantity": 2.0,
        "symbol": "AAPL",
        "avgPrice": 210.50,
        "conid": 265598,
    }]


@pytest.mark.asyncio
async def test_ibkr_broker_authoritative_position_hydration():
    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")
    from app.position_engine import PositionEngine

    engine = PositionEngine()
    ok = await adapter.hydrate_positions(
        engine,
        "IBKR-01",
        [{"asset": "AAPL", "symbol": "AAPL", "quantity": 2.0, "avgPrice": 210.50}],
    )

    assert ok is True
    position = engine.get("IBKR-01", "AAPL")
    assert position.quantity == 2.0
    assert position.average_entry == 210.50

@pytest.mark.asyncio
async def test_ibkr_short_position_fails_closed():
    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")
    from app.position_engine import PositionEngine

    ok = await adapter.hydrate_positions(
        PositionEngine(),
        "IBKR-01",
        [{"asset": "AAPL", "symbol": "AAPL", "quantity": -2.0, "avgPrice": 210.50}],
    )
    assert ok is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Submitted", "NEW"),
        ("PreSubmitted", "NEW"),
        ("PartiallyFilled", "PARTIALLY_FILLED"),
        ("Filled", "FILLED"),
        ("Cancelled", "CANCELED"),
        ("Inactive", "UNKNOWN"),
    ],
)
def test_ibkr_order_status_mapping(raw, expected):
    assert IBKRAdapter._map_order_status(raw) == expected


@pytest.mark.asyncio
async def test_ibkr_open_orders_are_normalized(monkeypatch):
    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")

    async def fake_request(method, path, *, json=None):
        assert method == "GET"
        assert path == "/v1/api/iserver/account/orders"
        return {
            "orders": [
                {
                    "orderId": 42,
                    "orderRef": "GMAI-42",
                    "ticker": "AAPL",
                    "side": "BUY",
                    "status": "PartiallyFilled",
                    "totalQuantity": "2",
                    "filledQuantity": "0.5",
                    "avgPrice": "210.25",
                }
            ]
        }

    monkeypatch.setattr(adapter, "_request", fake_request)
    orders = await adapter.get_open_orders()

    assert orders == [{
        "clientOrderId": "GMAI-42",
        "symbol": "AAPL",
        "side": "BUY",
        "status": "PARTIALLY_FILLED",
        "origQty": 2.0,
        "executedQty": 0.5,
        "avgPrice": 210.25,
        "orderId": "42",
    }]


@pytest.mark.asyncio
async def test_ibkr_place_order_propagates_client_order_id(monkeypatch):
    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")

    captured = {}

    async def fake_request(method, path, *, json=None):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = json
        return [{"order_id": "9001", "local_order_id": "GMAI-9001", "order_status": "Submitted"}]

    monkeypatch.setattr(adapter, "_request", fake_request)
    result = await adapter.place_order(
        "AAPL", "BUY", 1.0, order_type="MARKET",
        conid=265598, client_order_id="GMAI-9001",
    )

    payload = captured["json"]["orders"][0]
    assert payload["cOID"] == "GMAI-9001"
    assert captured["method"] == "POST"
    assert result[0]["local_order_id"] == "GMAI-9001"


@pytest.mark.asyncio
async def test_ibkr_order_lookup_uses_client_order_reference(monkeypatch):
    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")

    async def fake_request(method, path, *, json=None):
        return {
            "orders": [
                {
                    "orderId": 9001,
                    "ticker": "AAPL",
                    "side": "BUY",
                    "status": "Submitted",
                    "totalQuantity": 1,
                    "filledQuantity": 0,
                    "order_ref": "GMAI-9001",
                }
            ]
        }

    monkeypatch.setattr(adapter, "_request", fake_request)
    order = await adapter.get_order_by_client_id("AAPL", "GMAI-9001")

    assert order is not None
    assert order["clientOrderId"] == "GMAI-9001"
    assert order["status"] == "NEW"


@pytest.mark.asyncio
async def test_ibkr_pending_lookup_finds_filled_order_from_account_monitor(monkeypatch):
    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")

    async def fake_request(method, path, *, json=None, params=None):
        assert method == "GET"
        assert path == "/v1/api/iserver/account/orders"
        return {
            "orders": [{
                "orderId": 9002,
                "ticker": "AAPL",
                "side": "BUY",
                "status": "Filled",
                "totalSize": "1",
                "filledQuantity": "1",
                "avgPrice": "211.10",
                "order_ref": "GMAI-9002",
            }]
        }

    monkeypatch.setattr(adapter, "_request", fake_request)
    order = await adapter.get_order_by_client_id("AAPL", "GMAI-9002")

    assert order is not None
    assert order["status"] == "FILLED"
    assert order["executedQty"] == 1.0
    assert order["avgPrice"] == 211.10

@pytest.mark.asyncio
async def test_ibkr_account_trades_are_normalized(monkeypatch):
    adapter = IBKRAdapter("IBKR-01", mode="DEMO", session_cookie="cookie")

    async def fake_request(method, path, *, json=None):
        assert method == "GET"
        assert path == "/v1/api/iserver/account/trades"
        return {
            "trades": [{
                "execution_id": "E-1",
                "order_ref": "GMAI-9003",
                "order_id": 9003,
                "symbol": "AAPL",
                "side": "BUY",
                "size": "1.0",
                "price": "211.25",
            }]
        }

    monkeypatch.setattr(adapter, "_request", fake_request)
    trades = await adapter.get_account_trades()

    assert trades == [{
        "executionId": "E-1",
        "clientOrderId": "GMAI-9003",
        "brokerOrderId": "9003",
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 1.0,
        "price": 211.25,
    }]
