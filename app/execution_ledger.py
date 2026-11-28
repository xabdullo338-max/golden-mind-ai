from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionLedger:
    """Cumulative execution ledger with optional durable persistence."""

    path: str = ":memory:"

    def __post_init__(self):
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path) if self.path == ":memory:" else None
        db = self._connect()
        try:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_facts (
                    broker TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    stable_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    PRIMARY KEY (broker, account_id, stable_id)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    broker TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    cumulative_executed REAL NOT NULL,
                    PRIMARY KEY (broker, account_id, order_id)
                )
                """
            )
            db.commit()
        finally:
            self._close(db)

    def _connect(self):
        return self._db if self._db is not None else sqlite3.connect(self.path)

    def _close(self, db):
        if self._db is None:
            db.close()

    def _key(self, order_id: str, account_id: str | None, broker: str | None):
        return (broker or "").upper(), account_id or "", order_id

    def delta(
        self,
        order_id: str,
        cumulative_executed: float,
        account_id: str | None = None,
        broker: str | None = None,
    ) -> float:
        if cumulative_executed < 0:
            raise ValueError("cumulative_executed cannot be negative")

        broker_key, account_key, order_key = self._key(
            order_id, account_id, broker
        )
        db = self._connect()
        try:
            row = db.execute(
                """
                SELECT cumulative_executed
                FROM executions
                WHERE broker=? AND account_id=? AND order_id=?
                """,
                (broker_key, account_key, order_key),
            ).fetchone()
            previous = float(row[0]) if row else 0.0

            if cumulative_executed < previous:
                raise ValueError("broker execution quantity moved backwards")

            delta = cumulative_executed - previous
            if row:
                db.execute(
                    """
                    UPDATE executions
                    SET cumulative_executed=?
                    WHERE broker=? AND account_id=? AND order_id=?
                    """,
                    (cumulative_executed, broker_key, account_key, order_key),
                )
            else:
                db.execute(
                    """
                    INSERT INTO executions(
                        broker, account_id, order_id, cumulative_executed
                    ) VALUES(?,?,?,?)
                    """,
                    (broker_key, account_key, order_key, cumulative_executed),
                )
            db.commit()
            return delta
        finally:
            self._close(db)

    def clear(
        self,
        order_id: str,
        account_id: str | None = None,
        broker: str | None = None,
    ) -> None:
        broker_key, account_key, order_key = self._key(
            order_id, account_id, broker
        )
        db = self._connect()
        try:
            db.execute(
                """
                DELETE FROM executions
                WHERE broker=? AND account_id=? AND order_id=?
                """,
                (broker_key, account_key, order_key),
            )
            db.commit()
        finally:
            self._close(db)


    def execution_correction_key(self, execution_id: str) -> str:
        """Return the stable IBKR execution key shared by an execution and its correction."""
        return str(execution_id).rsplit(".", 1)[0]

    def record_execution(
        self,
        execution_id: str,
        quantity: float,
        account_id: str,
        broker: str,
    ) -> tuple[float, bool]:
        """Record one execution version; corrections replace the prior version."""
        if quantity < 0:
            raise ValueError("execution quantity cannot be negative")
        stable = self.execution_correction_key(execution_id)
        broker_key, account_key, _ = self._key(stable, account_id, broker)
        db = self._connect()
        try:
            row = db.execute(
                "SELECT execution_id, quantity FROM execution_facts "
                "WHERE broker=? AND account_id=? AND stable_id=?",
                (broker_key, account_key, stable),
            ).fetchone()
            if row and str(row[0]) == str(execution_id):
                return 0.0, False
            previous = float(row[1]) if row else 0.0
            if row:
                db.execute(
                    "UPDATE execution_facts SET execution_id=?, quantity=? "
                    "WHERE broker=? AND account_id=? AND stable_id=?",
                    (str(execution_id), quantity, broker_key, account_key, stable),
                )
            else:
                db.execute(
                    "INSERT INTO execution_facts(broker,account_id,stable_id,execution_id,quantity) "
                    "VALUES(?,?,?,?,?)",
                    (broker_key, account_key, stable, str(execution_id), quantity),
                )
            db.commit()
            return quantity - previous, True
        finally:
            self._close(db)
