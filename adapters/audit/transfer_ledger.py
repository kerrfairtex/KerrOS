"""
adapters/audit/transfer_ledger.py
=================================
Cross-border transfer *intent* ledger for decision_log evidence (ADR-026)
plus execution status updates (ADR-027).

Default-off. Append-only inserts for intents; ``mark_status`` updates
execution state after the pipeline copies evidence (sources untouched).
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

MECHANISMS = (
    "scc",
    "adequacy",
    "consent",
    "derogation",
    "internal",
)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class TransferConfig:
    enabled: bool = False
    db_path: str = "data/transfer_requests.db"
    default_from_region: str = ""


def transfer_config_from(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> TransferConfig:
    data = dict(cfg or {})
    raw = dict(data.get("audit_transfers") or {})
    residency = dict(data.get("audit_residency") or {})

    enabled = raw.get("enabled", False)
    env = os.environ.get("KERROS_AUDIT_TRANSFERS")
    if env is not None:
        enabled = _truthy(env)
    else:
        enabled = _truthy(enabled)

    db_path = os.environ.get("KERROS_AUDIT_TRANSFERS_DB")
    if db_path is None:
        db_path = str(raw.get("db_path") or "data/transfer_requests.db")

    from_region = os.environ.get("KERROS_AUDIT_TRANSFER_FROM")
    if from_region is None:
        from_region = str(
            raw.get("default_from_region")
            or residency.get("region")
            or ""
        )

    db = Path(db_path)
    if base is not None and not db.is_absolute():
        db = Path(base) / db

    return TransferConfig(
        enabled=bool(enabled),
        db_path=str(db),
        default_from_region=str(from_region or "").strip(),
    )


class TransferLedger:
    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transfer_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_at REAL NOT NULL,
                    from_region TEXT NOT NULL,
                    to_region TEXT NOT NULL,
                    mechanism TEXT NOT NULL,
                    subject_ref TEXT NOT NULL DEFAULT '',
                    purpose TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'recorded',
                    notes TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.commit()

    def record(
        self,
        *,
        from_region: str,
        to_region: str,
        mechanism: str,
        subject_ref: str = "",
        purpose: str = "",
        notes: str = "",
        actor: str = "",
        status: str = "recorded",
    ) -> dict[str, Any]:
        fr = str(from_region or "").strip()
        to = str(to_region or "").strip()
        mech = str(mechanism or "").strip().lower()
        if not fr or not to:
            raise ValueError("from_region and to_region required")
        if mech not in MECHANISMS:
            raise ValueError(
                f"invalid mechanism {mechanism!r}; expected one of {list(MECHANISMS)}"
            )
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO transfer_requests
                    (requested_at, from_region, to_region, mechanism,
                     subject_ref, purpose, status, notes, actor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    fr,
                    to,
                    mech,
                    str(subject_ref or ""),
                    str(purpose or ""),
                    str(status or "recorded"),
                    str(notes or ""),
                    str(actor or ""),
                ),
            )
            conn.commit()
            rid = int(cur.lastrowid)
        return self.get(rid)

    def get(self, request_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM transfer_requests WHERE id = ?",
                (int(request_id),),
            ).fetchone()
        if row is None:
            raise KeyError(f"transfer request {request_id} not found")
        return dict(row)

    def mark_status(
        self,
        request_id: int,
        status: str,
        *,
        notes: str = "",
    ) -> dict[str, Any]:
        """Update status on an existing intent (ADR-027 execution)."""
        st = str(status or "").strip().lower()
        if st not in ("recorded", "executed", "failed", "cancelled"):
            raise ValueError(f"invalid transfer status: {status!r}")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT notes FROM transfer_requests WHERE id = ?",
                (int(request_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"transfer request {request_id} not found")
            prev_notes = str(row["notes"] or "")
            merged = prev_notes
            if notes:
                merged = (prev_notes + " | " if prev_notes else "") + str(notes)
            conn.execute(
                """
                UPDATE transfer_requests
                SET status = ?, notes = ?
                WHERE id = ?
                """,
                (st, merged, int(request_id)),
            )
            conn.commit()
        return self.get(int(request_id))

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM transfer_requests
                ORDER BY id DESC LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(r) for r in rows]


def record_transfer_intent(
    *,
    to_region: str,
    mechanism: str,
    from_region: str = "",
    subject_ref: str = "",
    purpose: str = "",
    notes: str = "",
    actor: str = "",
    cfg: Optional[Mapping[str, Any]] = None,
    base: Optional[Path] = None,
    audit_token: Optional[str] = None,
    skip_rbac: bool = False,
) -> dict[str, Any]:
    """Record a cross-border transfer intent (does not move evidence bytes)."""
    if not skip_rbac:
        from adapters.audit.rbac import require_audit_action

        require_audit_action("transfer_record", token=audit_token, cfg=cfg)

    tcfg = transfer_config_from(cfg, base=base)
    if not tcfg.enabled:
        return {
            "ok": False,
            "error": "audit_transfers disabled",
            "enabled": False,
        }

    fr = str(from_region or "").strip() or tcfg.default_from_region
    if not fr:
        return {
            "ok": False,
            "error": "from_region required (or set audit_residency.region)",
        }

    to = str(to_region or "").strip()
    cross_border = fr.upper() != to.upper()
    ledger = TransferLedger(tcfg.db_path)
    try:
        row = ledger.record(
            from_region=fr,
            to_region=to,
            mechanism=mechanism,
            subject_ref=subject_ref,
            purpose=purpose,
            notes=notes,
            actor=actor,
            status="recorded",
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "enabled": True,
        "transfer": row,
        "cross_border": cross_border,
        "policy": (
            "cross_border_intent_recorded"
            if cross_border
            else "same_region_intent_recorded"
        ),
        "note": "ledger only — operator must execute the transfer channel",
    }
