"""
adapters/audit/erasure_ledger.py
================================
Lawful erasure *request* ledger for decision_log (ADR-025).

Append-only side SQLite. Records subject-rights requests and evaluates
whether hot-store follow-up is possible. **Never** rewrites sealed WORM
segments. Hot prefix-delete remains behind ADR-019 retention only.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from adapters.audit.worm_store import WormStore


STATUSES = (
    "recorded",
    "blocked_sealed",
    "eligible_hot_retention",
    "completed_via_retention",
    "rejected",
    # ADR-026 sealed-cold review outcomes (append-only follow-up rows)
    "review_legal_hold_retain",
    "review_acknowledged_immutable",
    "review_schedule_post_retention",
)

REVIEW_OUTCOMES = (
    "legal_hold_retain",
    "acknowledged_immutable",
    "schedule_post_retention",
)

_REVIEW_STATUS = {
    "legal_hold_retain": "review_legal_hold_retain",
    "acknowledged_immutable": "review_acknowledged_immutable",
    "schedule_post_retention": "review_schedule_post_retention",
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class ErasureConfig:
    enabled: bool = False
    db_path: str = "data/erasure_requests.db"
    worm_dir: str = "data/audit_worm"


def erasure_config_from(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> ErasureConfig:
    data = dict(cfg or {})
    raw = dict(data.get("audit_erasure") or {})
    retention = dict(data.get("audit_retention") or {})

    enabled = raw.get("enabled", False)
    env = os.environ.get("KERROS_AUDIT_ERASURE")
    if env is not None:
        enabled = _truthy(env)
    else:
        enabled = _truthy(enabled)

    db_path = os.environ.get("KERROS_AUDIT_ERASURE_DB")
    if db_path is None:
        db_path = str(raw.get("db_path") or "data/erasure_requests.db")
    worm_dir = os.environ.get("KERROS_AUDIT_WORM_DIR")
    if worm_dir is None:
        worm_dir = str(
            raw.get("worm_dir")
            or retention.get("worm_dir")
            or "data/audit_worm"
        )

    db = Path(db_path)
    worm = Path(worm_dir)
    if base is not None:
        if not db.is_absolute():
            db = Path(base) / db
        if not worm.is_absolute():
            worm = Path(base) / worm

    return ErasureConfig(
        enabled=bool(enabled),
        db_path=str(db),
        worm_dir=str(worm),
    )


class ErasureLedger:
    """Append-only erasure request store."""

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
                CREATE TABLE IF NOT EXISTS erasure_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_at REAL NOT NULL,
                    subject_ref TEXT NOT NULL,
                    legal_basis TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    decision_ids TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT '',
                    sealed_overlap INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def record(
        self,
        *,
        subject_ref: str,
        legal_basis: str = "",
        decision_ids: Optional[Sequence[int]] = None,
        notes: str = "",
        actor: str = "",
        status: str = "recorded",
        sealed_overlap: bool = False,
    ) -> dict[str, Any]:
        subj = str(subject_ref or "").strip()
        if not subj:
            raise ValueError("subject_ref required")
        st = str(status or "recorded").strip().lower()
        if st not in STATUSES:
            raise ValueError(f"invalid erasure status: {status!r}")
        ids = ",".join(str(int(i)) for i in (decision_ids or []))
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO erasure_requests
                    (requested_at, subject_ref, legal_basis, status,
                     decision_ids, notes, actor, sealed_overlap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    subj,
                    str(legal_basis or ""),
                    st,
                    ids,
                    str(notes or ""),
                    str(actor or ""),
                    1 if sealed_overlap else 0,
                ),
            )
            conn.commit()
            rid = int(cur.lastrowid)
        return self.get(rid)

    def get(self, request_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM erasure_requests WHERE id = ?",
                (int(request_id),),
            ).fetchone()
        if row is None:
            raise KeyError(f"erasure request {request_id} not found")
        return _row_dict(row)

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM erasure_requests
                ORDER BY id DESC LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [_row_dict(r) for r in rows]


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    ids_raw = str(data.get("decision_ids") or "")
    data["decision_id_list"] = [
        int(x) for x in ids_raw.split(",") if x.strip().isdigit()
    ]
    data["sealed_overlap"] = bool(data.get("sealed_overlap"))
    return data


def sealed_id_ranges(worm: WormStore) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for seg in worm.list_segments():
        first = int(seg.get("first_id") or 0)
        last = int(seg.get("last_id") or 0)
        if first and last and last >= first:
            ranges.append((first, last))
    return ranges


def ids_overlap_sealed(
    decision_ids: Sequence[int], ranges: Sequence[tuple[int, int]]
) -> list[int]:
    hit: list[int] = []
    for did in decision_ids:
        n = int(did)
        for first, last in ranges:
            if first <= n <= last:
                hit.append(n)
                break
    return hit


def evaluate_erasure_request(
    *,
    subject_ref: str,
    decision_ids: Optional[Sequence[int]] = None,
    legal_basis: str = "",
    notes: str = "",
    actor: str = "",
    cfg: Optional[Mapping[str, Any]] = None,
    base: Optional[Path] = None,
    audit_token: Optional[str] = None,
    skip_rbac: bool = False,
) -> dict[str, Any]:
    """
    Record an erasure request and classify against sealed WORM ranges.

    Does **not** delete hot or cold evidence. Operator may later run
    retention archive/purge for eligible hot prefixes.
    """
    if not skip_rbac:
        from adapters.audit.rbac import require_audit_action

        require_audit_action("erasure_request", token=audit_token, cfg=cfg)

    eco = erasure_config_from(cfg, base=base)
    if not eco.enabled:
        return {
            "ok": False,
            "error": "audit_erasure disabled",
            "enabled": False,
        }

    ids = [int(i) for i in (decision_ids or [])]
    worm = WormStore(eco.worm_dir)
    ranges = sealed_id_ranges(worm)
    overlap = ids_overlap_sealed(ids, ranges) if ids else []

    if overlap:
        status = "blocked_sealed"
        note = (
            (notes + " | " if notes else "")
            + f"sealed overlap ids={overlap}; WORM not rewritten (ADR-025)"
        )
    elif ids:
        status = "eligible_hot_retention"
        note = notes
    else:
        status = "recorded"
        note = notes or "no decision_ids supplied — ledger only"

    ledger = ErasureLedger(eco.db_path)
    row = ledger.record(
        subject_ref=subject_ref,
        legal_basis=legal_basis,
        decision_ids=ids,
        notes=note,
        actor=actor,
        status=status,
        sealed_overlap=bool(overlap),
    )
    return {
        "ok": True,
        "enabled": True,
        "request": row,
        "sealed_ranges": [{"first_id": a, "last_id": b} for a, b in ranges],
        "overlap_ids": overlap,
        "policy": (
            "blocked_sealed_no_worm_rewrite"
            if overlap
            else (
                "eligible_for_retention_followup"
                if ids
                else "recorded_only"
            )
        ),
    }


def review_sealed_erasure(
    request_id: int,
    *,
    outcome: str,
    notes: str = "",
    actor: str = "",
    cfg: Optional[Mapping[str, Any]] = None,
    base: Optional[Path] = None,
    audit_token: Optional[str] = None,
    skip_rbac: bool = False,
) -> dict[str, Any]:
    """
    Append a sealed-cold review outcome for a ``blocked_sealed`` request (ADR-026).

    Never rewrites WORM. Creates a new ledger row linked by subject_ref /
    decision_ids copied from the parent request.
    """
    if not skip_rbac:
        from adapters.audit.rbac import require_audit_action

        require_audit_action("erasure_review", token=audit_token, cfg=cfg)

    eco = erasure_config_from(cfg, base=base)
    if not eco.enabled:
        return {
            "ok": False,
            "error": "audit_erasure disabled",
            "enabled": False,
        }

    key = str(outcome or "").strip().lower()
    if key not in _REVIEW_STATUS:
        return {
            "ok": False,
            "error": (
                f"invalid review outcome {outcome!r}; "
                f"expected one of {list(REVIEW_OUTCOMES)}"
            ),
        }

    ledger = ErasureLedger(eco.db_path)
    try:
        parent = ledger.get(int(request_id))
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}

    if parent.get("status") != "blocked_sealed" and not parent.get("sealed_overlap"):
        return {
            "ok": False,
            "error": (
                f"request #{request_id} is not blocked_sealed "
                f"(status={parent.get('status')})"
            ),
        }

    # Verify WORM still intact for overlap ids (no rewrite happened).
    worm = WormStore(eco.worm_dir)
    ranges = sealed_id_ranges(worm)
    overlap = ids_overlap_sealed(parent.get("decision_id_list") or [], ranges)
    if not overlap and parent.get("decision_id_list"):
        return {
            "ok": False,
            "error": "no sealed overlap remains — use hot retention path instead",
        }

    status = _REVIEW_STATUS[key]
    note = (
        f"review of erasure #{request_id}: {key}"
        + (f" | {notes}" if notes else "")
        + " | sealed WORM not rewritten (ADR-026)"
    )
    row = ledger.record(
        subject_ref=str(parent.get("subject_ref") or ""),
        legal_basis=str(parent.get("legal_basis") or ""),
        decision_ids=list(parent.get("decision_id_list") or []),
        notes=note,
        actor=actor or "reviewer",
        status=status,
        sealed_overlap=True,
    )

    # Confirm segments still verify when present.
    segment_ok = True
    for seg in worm.list_segments():
        v = worm.verify_segment(int(seg.get("segment") or 0))
        if not v.get("ok"):
            segment_ok = False
            break

    return {
        "ok": True,
        "enabled": True,
        "parent_id": int(request_id),
        "outcome": key,
        "review": row,
        "overlap_ids": overlap,
        "worm_untouched": True,
        "worm_verify_ok": segment_ok,
        "policy": "sealed_cold_review_no_worm_rewrite",
    }
