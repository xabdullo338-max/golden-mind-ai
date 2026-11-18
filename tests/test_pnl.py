from app.pnl import Fill, FillLedger

def test_realized_pnl_net_of_commission():
    l = FillLedger()
    l.add(Fill("b", "BTCUSDT", "BUY", 1, 100, 1))
    l.add(Fill("s", "BTCUSDT", "SELL", 1, 110, 1))
    p = l.realized_pnl("BTCUSDT")
    assert p.gross_pnl == 10
    assert p.commission == 2
    assert p.net_pnl == 8