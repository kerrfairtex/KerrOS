"""
adapters/database/sqlite_adapter.py
===================================
DatabasePort adapter implementing local SQLite relational access.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, List
from ports.database_port import DatabasePort


class SQLiteAdapter(DatabasePort):
    """Local SQLite database adapter."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self.db_path = Path("data") / "sqlite_db.sqlite"
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_conn()

    def _init_conn(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def execute(self, query: str, params: tuple | None = None) -> None:
        p = params or ()
        with self._connect() as conn:
            conn.execute(query, p)
            conn.commit()

    def fetch_all(self, query: str, params: tuple | None = None) -> List[dict[str, Any]]:
        p = params or ()
        with self._connect() as conn:
            cur = conn.execute(query, p)
            rows = cur.fetchall()
            return [dict(row) for row in rows]

    def fetch_one(self, query: str, params: tuple | None = None) -> dict[str, Any] | None:
        p = params or ()
        with self._connect() as conn:
            cur = conn.execute(query, p)
            row = cur.fetchone()
            return dict(row) if row else None
