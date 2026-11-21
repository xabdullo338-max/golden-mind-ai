from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionLedger:
    """Durable cumulative execution ledger.

    The broker's cumulative executed quantity is persisted so a process restart
    or websocket reconnect cannot cause an already-applied fill to be applied
    to positions a second time.
    """

    path: str = "data/golden_mind_execution.db"

    def __post_init__(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
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

    def _key(self, order_id: str, account_id: str | None, broker: str | None):
        return (
            (broker or "").upper(),
            account_id or "",
            order_id,
        )

    def delta(
        self,
        order_id: str,
        cumulative_executed: float,
        account_id: str | None = None,
        broker: str | None = None,
    ) -> float:
        if cumulative_executed < 0:
            raise ValueError("cumulative_executed cannot be negative")

        broker_key, account_key, order_key = self._key(order_id, account_id, broker)

        with sqlite3.connect(self.path) as db:
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

    def clear(
        self,
        order_id: str,
        account_id: str | None = None,
        broker: str | None = None,
    ) -> None:
        broker_key, account_key, order_key = self._key(order_id, account_id, broker)
        with sqlite3.connect(self.path) as db:
            db.execute(
                """
                DELETE FROM executions
                WHERE broker=? AND account_id=? AND order_id=?
                """,
                (broker_key, account_key, order_key),
            )
            db.commit()
