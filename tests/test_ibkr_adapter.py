import pytest
from app.brokers.ibkr import IBKRAdapter

@pytest.mark.asyncio
async def test_ibkr_paper_order_is_local():
    adapter = IBKRAdapter("IBKR-PAPER", mode="PAPER")
    result = await adapter.place_order("AAPL", "BUY", 1)
    assert result["status"] == "PAPER"
    assert result["broker"] == "IBKR"

@pytest.mark.asyncio
async def test_ibkr_execution_requires_session_cookie():
    adapter = IBKRAdapter("IBKR-01", mode="LIVE")
    with pytest.raises(RuntimeError):
        await adapter.place_order("AAPL", "BUY", 1, conid=265598)