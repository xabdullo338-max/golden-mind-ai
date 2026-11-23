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
    """Durable order journal with a broker/account-scoped primary key.

    Existing installations created with the original single-column
    client_order_id primary key are migrated in-place on startup.
    """

    def __init__(self, path: str = "data/golden_mind.db"):
        self.path = Path(path) if path != ":memory:" else None
        self._db = sqlite3.connect(":memory:") if path == ":memory:" else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        db = self._connect()
        try:
            self._ensure_schema(db)
            db.commit()
        finally:
            self._close(db)

    def _connect(self):
        return self._db if self._db is not None else sqlite3.connect(self.path)

    def _close(self, db):
        if self._db is None:
            db.close()

    @staticmethod
    def _table_columns(db: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
        rows = db.execute(f"PRAGMA table_info({table})").fetchall()
        return [
            {"name": row[1], "type": row[2], "notnull": row[3], "default": row[4], "pk": row[5]}
            for row in rows
        ]

    def _create_orders_table(self, db: sqlite3.Connection, table: str = "orders") -> None:
        db.execute(f"""CREATE TABLE {table} (
            client_order_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            broker TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            status TEXT NOT NULL,
            broker_order_id TEXT,
            PRIMARY KEY (broker, account_id, client_order_id)
        )""")

    def _ensure_schema(self, db: sqlite3.Connection) -> None:
        columns = self._table_columns(db, "orders")
        if not columns:
            self._create_orders_table(db)
            return

        names = {column["name"] for column in columns}
        pk = {column["name"] for column in columns if column["pk"]}

        required = {
            "client_order_id", "account_id", "broker", "symbol",
            "side", "quantity", "status", "broker_order_id",
        }
        if required.issubset(names) and pk == {"broker", "account_id", "client_order_id"}:
            return

        # Migrate the pre-account-scoped schema without discarding journal data.
        db.execute("ALTER TABLE orders RENAME TO orders_legacy")
        self._create_orders_table(db)

        legacy_columns = {column["name"] for column in self._table_columns(db, "orders_legacy")}
        required_legacy = {"client_order_id", "symbol", "side", "quantity", "status"}
        if not required_legacy.issubset(legacy_columns):
            raise RuntimeError("Unsupported legacy orders schema")

        account_expr = "account_id" if "account_id" in legacy_columns else "'LEGACY'"
        broker_expr = "broker" if "broker" in legacy_columns else "'LEGACY'"
        broker_order_expr = "broker_order_id" if "broker_order_id" in legacy_columns else "NULL"

        db.execute(
            f"""INSERT INTO orders(
                    client_order_id, account_id, broker, symbol, side,
                    quantity, status, broker_order_id
                )
                SELECT client_order_id, {account_expr}, {broker_expr}, symbol, side,
                       quantity, status, {broker_order_expr}
                FROM orders_legacy"""
        )
        db.execute("DROP TABLE orders_legacy")

    def upsert_order(self, order: JournalOrder) -> None:
        db = self._connect()
        try:
            db.execute(
                """INSERT INTO orders(
                    client_order_id,account_id,broker,symbol,side,quantity,status,broker_order_id
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(broker, account_id, client_order_id) DO UPDATE SET
                    status=excluded.status,
                    broker_order_id=excluded.broker_order_id,
                    quantity=excluded.quantity""",
                (
                    order.client_order_id, order.account_id, order.broker, order.symbol,
                    order.side, order.quantity, order.status, order.broker_order_id,
                ),
            )
            db.commit()
        finally:
            self._close(db)

    def get_order(
        self,
        client_order_id: str,
        account_id: str | None = None,
        broker: str | None = None,
    ) -> dict[str, Any] | None:
        db = self._connect()
        try:
            db.row_factory = sqlite3.Row
            if account_id and broker:
                row = db.execute(
                    "SELECT * FROM orders WHERE client_order_id=? AND account_id=? AND broker=?",
                    (client_order_id, account_id, broker),
                ).fetchone()
            else:
                rows = db.execute(
                    "SELECT * FROM orders WHERE client_order_id=? LIMIT 2",
                    (client_order_id,),
                ).fetchall()
                if len(rows) > 1:
                    raise ValueError("account_id and broker are required when client_order_id is not unique")
                row = rows[0] if rows else None
            return dict(row) if row else None
        finally:
            self._close(db)

    def list_open_orders(self) -> list[dict[str, Any]]:
        terminal = ("FILLED", "CANCELED", "REJECTED", "EXPIRED")
        db = self._connect()
        try:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM orders WHERE status NOT IN (?,?,?,?)",
                terminal,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            self._close(db)
