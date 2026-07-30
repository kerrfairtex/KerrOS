"""
kernel/decision_log.py
======================
Append-only SQLite decision log (KOS-008) with tamper-evidence hash chain
and export helpers (ADR-017 / LGU foundation).

Cold WORM segments + retention prefix-delete are ADR-019
(``delete_through(..., _retention=True)`` only).

Records scope gate, deploy arm/disarm, verification, watchdog, and
port-level audit events. No public UPDATE or DELETE API — audit trail is
append-only at the application layer. Schema migration may one-time
backfill hashes for pre-ADR-017 rows (user_version < 2).
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from kernel.config import load_config

GENESIS_HASH = "0" * 64
# v2 = prev_hash / entry_hash columns + one-time chain backfill (ADR-017)
SCHEMA_USER_VERSION = 2


@dataclass
class DecisionRecord:
    id: int
    timestamp: float
    actor: str
    decision_type: str
    input_summary: str
    outcome: str
    reason: str
    prev_hash: str = ""
    entry_hash: str = ""


def canonical_payload(
    timestamp: float,
    actor: str,
    decision_type: str,
    input_summary: str,
    outcome: str,
    reason: str,
) -> str:
    """Stable string used as the hash preimage (excluding id / hashes)."""
    return (
        f"{float(timestamp):.6f}|{actor}|{decision_type}|"
        f"{input_summary}|{outcome}|{reason}"
    )


def compute_entry_hash(prev_hash: str, payload: str) -> str:
    material = f"{prev_hash or GENESIS_HASH}|{payload}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class DecisionLog:
    """Append-only decision log backed by SQLite WAL + hash chain."""

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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        actor TEXT NOT NULL,
                        decision_type TEXT NOT NULL,
                        input_summary TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        reason TEXT NOT NULL DEFAULT '',
                        prev_hash TEXT NOT NULL DEFAULT '',
                        entry_hash TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
            self._migrate_hash_columns(conn)
            ver = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if ver < SCHEMA_USER_VERSION:
                self._backfill_hash_chain(conn)
                conn.execute(f"PRAGMA user_version = {SCHEMA_USER_VERSION}")
            conn.commit()

    @staticmethod
    def _migrate_hash_columns(conn: sqlite3.Connection) -> None:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(decisions)").fetchall()
        }
        if "prev_hash" not in cols:
            conn.execute(
                "ALTER TABLE decisions ADD COLUMN prev_hash TEXT NOT NULL DEFAULT ''"
            )
        if "entry_hash" not in cols:
            conn.execute(
                "ALTER TABLE decisions ADD COLUMN entry_hash TEXT NOT NULL DEFAULT ''"
            )

    @staticmethod
    def _backfill_hash_chain(conn: sqlite3.Connection) -> None:
        """One-time migration: fill hashes for pre-ADR-017 rows."""
        rows = conn.execute(
            """
            SELECT id, timestamp, actor, decision_type, input_summary,
                   outcome, reason
            FROM decisions
            ORDER BY id ASC
            """
        ).fetchall()
        prev = GENESIS_HASH
        for row in rows:
            payload = canonical_payload(
                row["timestamp"],
                row["actor"],
                row["decision_type"],
                row["input_summary"],
                row["outcome"],
                row["reason"],
            )
            entry = compute_entry_hash(prev, payload)
            conn.execute(
                """
                UPDATE decisions
                SET prev_hash = ?, entry_hash = ?
                WHERE id = ?
                """,
                (prev, entry, row["id"]),
            )
            prev = entry

    def _row_to_record(self, row: sqlite3.Row) -> DecisionRecord:
        keys = row.keys()
        return DecisionRecord(
            id=row["id"],
            timestamp=row["timestamp"],
            actor=row["actor"],
            decision_type=row["decision_type"],
            input_summary=row["input_summary"],
            outcome=row["outcome"],
            reason=row["reason"],
            prev_hash=row["prev_hash"] if "prev_hash" in keys else "",
            entry_hash=row["entry_hash"] if "entry_hash" in keys else "",
        )

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
            conn.execute("BEGIN IMMEDIATE")
            last = conn.execute(
                """
                SELECT entry_hash FROM decisions
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            prev = (
                last["entry_hash"]
                if last and last["entry_hash"]
                else GENESIS_HASH
            )
            payload = canonical_payload(
                ts, actor, decision_type, input_summary, outcome, reason
            )
            entry = compute_entry_hash(prev, payload)
            cur = conn.execute(
                """
                INSERT INTO decisions
                    (timestamp, actor, decision_type, input_summary,
                     outcome, reason, prev_hash, entry_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    actor,
                    decision_type,
                    input_summary,
                    outcome,
                    reason,
                    prev,
                    entry,
                ),
            )
            conn.commit()
            rid = int(cur.lastrowid)
        # ADR-021: best-effort SIEM — never fail the append path.
        # ADR-024: redact egress payload when audit_privacy enabled for siem.
        try:
            from adapters.audit.privacy import maybe_redact_mapping
            from adapters.audit.siem_forwarder import get_siem_forwarder

            get_siem_forwarder().forward_record(
                maybe_redact_mapping(
                    {
                        "id": rid,
                        "timestamp": ts,
                        "actor": actor,
                        "decision_type": decision_type,
                        "input_summary": input_summary,
                        "outcome": outcome,
                        "reason": reason,
                        "prev_hash": prev,
                        "entry_hash": entry,
                    },
                    channel="siem",
                )
            )
        except Exception:
            pass
        return rid

    def read_recent(self, limit: int = 50) -> list[DecisionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, actor, decision_type, input_summary,
                       outcome, reason, prev_hash, entry_hash
                FROM decisions
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def iter_from(self, since_id: int = 0) -> Iterator[DecisionRecord]:
        """Yield records with id > since_id in ascending id order (export)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, actor, decision_type, input_summary,
                       outcome, reason, prev_hash, entry_hash
                FROM decisions
                WHERE id > ?
                ORDER BY id ASC
                """,
                (int(since_id),),
            ).fetchall()
        for row in rows:
            yield self._row_to_record(row)

    def iter_through(self, through_id: int) -> Iterator[DecisionRecord]:
        """Yield records with id <= through_id in ascending id order."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, actor, decision_type, input_summary,
                       outcome, reason, prev_hash, entry_hash
                FROM decisions
                WHERE id <= ?
                ORDER BY id ASC
                """,
                (int(through_id),),
            ).fetchall()
        for row in rows:
            yield self._row_to_record(row)

    def retention_cutoff_id(self, cutoff_ts: float) -> int | None:
        """Largest id in the oldest contiguous prefix with timestamp < cutoff_ts."""
        last: int | None = None
        for rec in self.iter_from(0):
            if rec.timestamp < float(cutoff_ts):
                last = rec.id
            else:
                break
        return last

    def delete_through(self, last_id: int, *, _retention: bool = False) -> int:
        """
        Delete rows with id <= last_id.

        Retention-only (ADR-019). Callers must pass ``_retention=True`` after a
        successful WORM seal (or explicit purge). Not part of the public
        append-only API.
        """
        if not _retention:
            raise RuntimeError(
                "delete_through is retention-only — pass _retention=True "
                "(ADR-019) after sealing to WORM or intentional purge"
            )
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM decisions WHERE id <= ?",
                (int(last_id),),
            )
            conn.commit()
            return int(cur.rowcount or 0)

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()
        return int(row["n"])

    def verify_chain(self) -> dict[str, Any]:
        """
        Walk the hash chain. Returns ok + first failure detail if any.

        Empty log is valid. After ADR-019 archive, the first remaining row may
        anchor ``prev_hash`` to a sealed segment tip (not GENESIS).
        """
        checked = 0
        expected_prev: str | None = None
        tip = GENESIS_HASH
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, actor, decision_type, input_summary,
                       outcome, reason, prev_hash, entry_hash
                FROM decisions
                ORDER BY id ASC
                """
            ).fetchall()
        for row in rows:
            checked += 1
            prev = row["prev_hash"] or GENESIS_HASH
            if expected_prev is not None and prev != expected_prev:
                return {
                    "ok": False,
                    "checked": checked,
                    "broken_at": row["id"],
                    "error": "prev_hash mismatch",
                    "expected_prev": expected_prev,
                    "actual_prev": prev,
                }
            payload = canonical_payload(
                row["timestamp"],
                row["actor"],
                row["decision_type"],
                row["input_summary"],
                row["outcome"],
                row["reason"],
            )
            expected = compute_entry_hash(prev, payload)
            actual = row["entry_hash"] or ""
            if actual != expected:
                return {
                    "ok": False,
                    "checked": checked,
                    "broken_at": row["id"],
                    "error": "entry_hash mismatch",
                    "expected_hash": expected,
                    "actual_hash": actual,
                }
            expected_prev = actual
            tip = actual
        return {
            "ok": True,
            "checked": checked,
            "tip": tip if checked else GENESIS_HASH,
        }

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
                "prev_hash": r.prev_hash,
                "entry_hash": r.entry_hash,
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
