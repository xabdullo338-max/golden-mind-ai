import hashlib
import hmac
from urllib.parse import parse_qs, urlparse
import pytest
from app.brokers.binance import BinanceAdapter

def test_binance_signature_is_hmac_sha256():
    adapter = BinanceAdapter("BINANCE-TEST", "key", "secret", mode="TESTNET")
    signed = adapter._signed_query({"symbol": "BTCUSDT", "side": "BUY"})
    query, signature = signed.split("&signature=")
    expected = hmac.new(b"secret", query.encode(), hashlib.sha256).hexdigest()
    assert signature == expected
    assert parse_qs(urlparse("?" + signed).query)["symbol"] == ["BTCUSDT"]

@pytest.mark.asyncio
async def test_paper_order_never_calls_exchange():
    adapter = BinanceAdapter("BINANCE-PAPER", "key", "secret", mode="PAPER")
    result = await adapter.place_order("BTCUSDT", "BUY", 0.001)
    assert result["status"] == "PAPER"

@pytest.mark.asyncio
async def test_live_requires_explicit_flag(monkeypatch):
    monkeypatch.delenv("GMAI_LIVE_TRADING", raising=False)
    adapter = BinanceAdapter("BINANCE-LIVE", "key", "secret",
                             base_url="https://api.binance.com", mode="LIVE")
    result = await adapter.place_order("BTCUSDT", "BUY", 0.001)
    assert result["status"] == "PAPER"