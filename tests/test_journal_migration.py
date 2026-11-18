import sqlite3

from app.journal import JournalOrder, TradingJournal


def test_legacy_single_key_schema_migrates_without_losing_orders(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute(
            """CREATE TABLE orders (
                client_order_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                broker TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                status TEXT NOT NULL,
                broker_order_id TEXT
            )"""
        )
        db.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
            ("cid-1", "A", "BINANCE", "BTCUSDT", "BUY", 0.01, "FILLED", "42"),
        )
        db.commit()

    journal = TradingJournal(str(path))
    saved = journal.get_order("cid-1", account_id="A", broker="BINANCE")

    assert saved is not None
    assert saved["status"] == "FILLED"
    assert saved["broker_order_id"] == "42"

    journal.upsert_order(
        JournalOrder(
            client_order_id="cid-1",
            account_id="B",
            broker="IBKR",
            symbol="BTC",
            side="BUY",
            quantity=1.0,
            status="NEW",
        )
    )

    assert journal.get_order("cid-1", account_id="A", broker="BINANCE") is not None
    assert journal.get_order("cid-1", account_id="B", broker="IBKR") is not None


def test_new_schema_does_not_migrate_again(tmp_path):
    path = tmp_path / "new.db"
    journal = TradingJournal(str(path))
    journal.upsert_order(
        JournalOrder("cid-1", "A", "BINANCE", "BTCUSDT", "BUY", 0.01, "NEW")
    )
    journal.upsert_order(
        JournalOrder("cid-1", "B", "BINANCE", "BTCUSDT", "BUY", 0.02, "NEW")
    )

    with sqlite3.connect(path) as db:
        pk = {
            row[1]
            for row in db.execute("PRAGMA table_info(orders)")
            if row[5]
        }

    assert pk == {"broker", "account_id", "client_order_id"}
