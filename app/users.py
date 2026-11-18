from __future__ import annotations

import sqlite3
from pathlib import Path
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()

class UserStore:
    def __init__(self, path: str = "data/golden_mind_users.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0
            )""")
            db.commit()

    def create_user(self, username: str, password: str, role: str = "viewer") -> None:
        if not username.strip() or len(password) < 8:
            raise ValueError("username required and password must be at least 8 characters")
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                       (username.strip(), password_hash.hash(password), role))
            db.commit()

    def authenticate(self, username: str, password: str) -> dict | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT username,password_hash,role,disabled FROM users WHERE username=?",
                (username,)
            ).fetchone()
        if not row or row[3]:
            return None
        if not password_hash.verify(password, row[1]):
            return None
        return {"username": row[0], "role": row[2], "disabled": bool(row[3])}
