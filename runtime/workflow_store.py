"""
runtime/workflow_store.py
=========================
SQLite persistence for workflow run state (P3).

Survives process restart so incomplete runs can resume. Step results must be
JSON-serializable (non-JSON values are coerced via ``default=str``).
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    workflow TEXT NOT NULL,
    state TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    results_json TEXT NOT NULL DEFAULT '{}',
    completed_steps_json TEXT NOT NULL DEFAULT '[]',
    error TEXT NOT NULL DEFAULT '',
    started_at REAL,
    finished_at REAL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wf_runs_updated ON workflow_runs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_wf_runs_state ON workflow_runs(state);
"""


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, sort_keys=True)


def _loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback


@dataclass
class WorkflowRunStore:
    """Thin SQLite store for workflow run checkpoints."""

    db_path: Path

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def upsert(
        self,
        *,
        run_id: str,
        workflow: str,
        state: str,
        context: Optional[dict[str, Any]] = None,
        results: Optional[dict[str, Any]] = None,
        completed_steps: Optional[list[str]] = None,
        error: str = "",
        started_at: Optional[float] = None,
        finished_at: Optional[float] = None,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workflow_runs (
                    id, workflow, state, context_json, results_json,
                    completed_steps_json, error, started_at, finished_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    workflow=excluded.workflow,
                    state=excluded.state,
                    context_json=excluded.context_json,
                    results_json=excluded.results_json,
                    completed_steps_json=excluded.completed_steps_json,
                    error=excluded.error,
                    started_at=COALESCE(excluded.started_at, workflow_runs.started_at),
                    finished_at=excluded.finished_at,
                    updated_at=excluded.updated_at
                """,
                (
                    run_id,
                    workflow,
                    state,
                    _dumps(context or {}),
                    _dumps(results or {}),
                    _dumps(list(completed_steps or [])),
                    error or "",
                    started_at,
                    finished_at,
                    now,
                ),
            )
            conn.commit()

    def get(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_recent(
        self,
        *,
        limit: int = 20,
        state: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            if state:
                rows = conn.execute(
                    """
                    SELECT * FROM workflow_runs
                    WHERE state = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (state, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM workflow_runs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_incomplete(self, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM workflow_runs
                WHERE state IN ('pending', 'running', 'failed')
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "workflow": row["workflow"],
            "state": row["state"],
            "context": _loads(row["context_json"], {}),
            "results": _loads(row["results_json"], {}),
            "completed_steps": _loads(row["completed_steps_json"], []),
            "error": row["error"] or "",
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "updated_at": row["updated_at"],
        }
