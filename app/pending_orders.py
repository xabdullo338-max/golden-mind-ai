from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PendingOrder:
    broker: str
    account_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: float


class PendingOrderStore:
    """Durable registry for orders whose broker outcome is temporarily unknown."""

    def __init__(self, path: str = "data/golden_mind_pending_orders.db"):
        self.path = path
        self._db = sqlite3.connect(path) if path == ":memory:" else None
        db = self._connect()
        try:
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            db.execute("""
                CREATE TABLE IF NOT EXISTS pending_orders (
                    broker TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    client_order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    PRIMARY KEY (broker, account_id, client_order_id)
                )
            """)
            db.commit()
        finally:
            self._close(db)

    def _connect(self):
        return self._db if self._db is not None else sqlite3.connect(self.path)

    def _close(self, db):
        if self._db is None:
            db.close()

    def mark(self, order: PendingOrder) -> None:
        db = self._connect()
        try:
            db.execute("""
                INSERT OR REPLACE INTO pending_orders
                (broker, account_id, client_order_id, symbol, side, quantity)
                VALUES (?,?,?,?,?,?)
            """, (order.broker.upper(), order.account_id, order.client_order_id,
                  order.symbol.upper(), order.side.upper(), order.quantity))
            db.commit()
        finally:
            self._close(db)

    def resolve(self, account_id: str, client_order_id: str, broker: str) -> None:
        db = self._connect()
        try:
            db.execute("""
                DELETE FROM pending_orders
                WHERE broker=? AND account_id=? AND client_order_id=?
            """, (broker.upper(), account_id, client_order_id))
            db.commit()
        finally:
            self._close(db)

    def list_account(self, account_id: str, broker: str) -> list[PendingOrder]:
        db = self._connect()
        try:
            rows = db.execute("""
                SELECT broker, account_id, client_order_id, symbol, side, quantity
                FROM pending_orders
                WHERE broker=? AND account_id=?
                ORDER BY client_order_id
            """, (broker.upper(), account_id)).fetchall()
            return [PendingOrder(*row) for row in rows]
        finally:
            self._close(db)
