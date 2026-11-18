from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class JournalOrder:
    client_order_id: str
    account_id: str
    broker: str
    symbol: str
    side: str
    quantity: float
    status: str
    broker_order_id: str | None = None

class TradingJournal:
    def __init__(self, path: str = "data/golden_mind.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS orders (
                client_order_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, broker TEXT NOT NULL,
                symbol TEXT NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL, status TEXT NOT NULL,
                broker_order_id TEXT)""")
            db.commit()

    def _connect(self):
        return sqlite3.connect(self.path)

    def upsert_order(self, order: JournalOrder) -> None:
        with self._connect() as db:
            db.execute("""INSERT INTO orders(client_order_id,account_id,broker,symbol,side,quantity,status,broker_order_id)
                         VALUES(?,?,?,?,?,?,?,?)
                         ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status,
                         broker_order_id=excluded.broker_order_id, quantity=excluded.quantity""",
                       (order.client_order_id, order.account_id, order.broker, order.symbol,
                        order.side, order.quantity, order.status, order.broker_order_id))
            db.commit()

    def get_order(self, client_order_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM orders WHERE client_order_id=?", (client_order_id,)).fetchone()
            return dict(row) if row else None

    def list_open_orders(self) -> list[dict[str, Any]]:
        terminal = ("FILLED", "CANCELED", "REJECTED", "EXPIRED")
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM orders WHERE status NOT IN (?,?,?)", terminal[:3]).fetchall()
            return [dict(r) for r in rows]
