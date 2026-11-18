from app.journal import JournalOrder, TradingJournal

def test_journal_persists_order(tmp_path):
    journal = TradingJournal(str(tmp_path / "gmai.db"))
    journal.upsert_order(JournalOrder("cid", "A", "BINANCE", "BTCUSDT", "BUY", 0.1, "NEW"))
    journal.upsert_order(JournalOrder("cid", "A", "BINANCE", "BTCUSDT", "BUY", 0.1, "FILLED", "42"))
    saved = journal.get_order("cid")
    assert saved["status"] == "FILLED"
    assert saved["broker_order_id"] == "42"