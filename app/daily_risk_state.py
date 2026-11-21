from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class DailyRiskState:
    account_id: str
    utc_date: str
    start_equity: float


class DailyRiskStateStore:
    """Durable UTC-day starting-equity state used by risk checks."""

    def __init__(self, path: str = "data/golden_mind_risk.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_risk_state (
                    account_id TEXT PRIMARY KEY,
                    utc_date TEXT NOT NULL,
                    start_equity REAL NOT NULL
                )
                """
            )
            db.commit()

    def get(self, account_id: str, day: date) -> DailyRiskState | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT account_id, utc_date, start_equity "
                "FROM daily_risk_state WHERE account_id=?",
                (account_id,),
            ).fetchone()
        if row is None or row[1] != day.isoformat():
            return None
        return DailyRiskState(row[0], row[1], float(row[2]))

    def establish_if_missing(
        self,
        account_id: str,
        day: date,
        equity: float,
    ) -> DailyRiskState:
        if equity <= 0:
            raise ValueError("equity must be positive")
        current = self.get(account_id, day)
        if current is not None:
            return current

        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT account_id, utc_date, start_equity "
                "FROM daily_risk_state WHERE account_id=?",
                (account_id,),
            ).fetchone()
            if row is None or row[1] != day.isoformat():
                db.execute(
                    """
                    INSERT INTO daily_risk_state(account_id, utc_date, start_equity)
                    VALUES(?,?,?)
                    ON CONFLICT(account_id) DO UPDATE SET
                        utc_date=excluded.utc_date,
                        start_equity=excluded.start_equity
                    """,
                    (account_id, day.isoformat(), equity),
                )
                db.commit()
                return DailyRiskState(account_id, day.isoformat(), float(equity))
            return DailyRiskState(row[0], row[1], float(row[2]))
