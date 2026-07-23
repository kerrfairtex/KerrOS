"""
kernel/decision_log.py
======================
Append-only SQLite decision log (KOS-008).

Records scope gate, deploy arm/disarm, verification, and watchdog events.
No UPDATE or DELETE API — audit trail is immutable.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kernel.config import load_config


@dataclass
class DecisionRecord:
    id: int
    timestamp: float
    actor: str
    decision_type: str
    input_summary: str
    outcome: str
    reason: str


class DecisionLog:
    """Append-only decision log backed by SQLite WAL."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            cfg = load_config()
            db_path = cfg.base / "data" / "decision_log.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        schema_path = Path(__file__).parent / "decision_log_schema.sql"
        with self._connect() as conn:
            if schema_path.exists():
                conn.executescript(schema_path.read_text())
            else:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        actor TEXT NOT NULL,
                        decision_type TEXT NOT NULL,
                        input_summary TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        reason TEXT NOT NULL DEFAULT ''
                    )
                """)
            conn.commit()

    def record(
        self,
        actor: str,
        decision_type: str,
        input_summary: str,
        outcome: str,
        reason: str = "",
        *,
        timestamp: float | None = None,
    ) -> int:
        """Append a decision record. Returns the new row id."""
        ts = timestamp if timestamp is not None else time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO decisions
                    (timestamp, actor, decision_type, input_summary, outcome, reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ts, actor, decision_type, input_summary, outcome, reason),
            )
            conn.commit()
            return int(cur.lastrowid)

    def read_recent(self, limit: int = 50) -> list[DecisionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, actor, decision_type, input_summary, outcome, reason
                FROM decisions
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [
            DecisionRecord(
                id=row["id"],
                timestamp=row["timestamp"],
                actor=row["actor"],
                decision_type=row["decision_type"],
                input_summary=row["input_summary"],
                outcome=row["outcome"],
                reason=row["reason"],
            )
            for row in rows
        ]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()
        return int(row["n"])

    def to_dicts(self, limit: int = 50) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp,
                "actor": r.actor,
                "decision_type": r.decision_type,
                "input_summary": r.input_summary,
                "outcome": r.outcome,
                "reason": r.reason,
            }
            for r in self.read_recent(limit)
        ]


_log: DecisionLog | None = None


def get_decision_log() -> DecisionLog:
    global _log
    if _log is None:
        _log = DecisionLog()
    return _log


def record_decision(
    actor: str,
    decision_type: str,
    input_summary: str,
    outcome: str,
    reason: str = "",
) -> int:
    """Convenience wrapper for modules that cannot import DecisionLog directly."""
    try:
        return get_decision_log().record(
            actor, decision_type, input_summary, outcome, reason
        )
    except Exception:
        return -1
