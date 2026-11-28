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
