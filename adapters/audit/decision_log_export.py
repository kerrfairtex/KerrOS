"""
adapters/audit/decision_log_export.py
=====================================
External audit export for the decision log (ADR-017 / LGU foundation).

Writes append-oriented JSONL. Optional HMAC-SHA256 over each line when
``KERROS_AUDIT_HMAC_SECRET`` (or ``hmac_secret=``) is set — not a WORM
backend; operators still own durable offsite storage.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Optional, Union

from kernel.decision_log import DecisionLog, DecisionRecord


def record_dict(rec: DecisionRecord) -> dict[str, Any]:
    return {
        "id": rec.id,
        "timestamp": rec.timestamp,
        "actor": rec.actor,
        "decision_type": rec.decision_type,
        "input_summary": rec.input_summary,
        "outcome": rec.outcome,
        "reason": rec.reason,
        "prev_hash": rec.prev_hash,
        "entry_hash": rec.entry_hash,
    }


# Back-compat alias
_record_dict = record_dict


def resolve_hmac_secret(explicit: Optional[str] = None) -> str:
    if explicit is not None:
        return str(explicit).strip()
    return str(os.getenv("KERROS_AUDIT_HMAC_SECRET") or "").strip()


def line_hmac(line: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        line.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def export_decision_log_jsonl(
    dest: Union[str, Path],
    *,
    log: Optional[DecisionLog] = None,
    since_id: int = 0,
    hmac_secret: Optional[str] = None,
    verify_before_export: bool = True,
    audit_token: Optional[str] = None,
    skip_rbac: bool = False,
    privacy_cfg: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Export decisions with id > since_id to JSONL.

    Each line is one JSON object. When an HMAC secret is configured, each
    object gains ``line_hmac`` over the canonical JSON (without that field).
    ADR-024: optional egress privacy transform when ``audit_privacy`` enabled.
    """
    if not skip_rbac:
        from adapters.audit.rbac import require_audit_action

        require_audit_action("export", token=audit_token)

    decision_log = log or DecisionLog()
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)

    if verify_before_export:
        chain = decision_log.verify_chain()
        if not chain.get("ok"):
            return {
                "ok": False,
                "path": str(path),
                "exported": 0,
                "error": "chain verification failed",
                "chain": chain,
            }

    secret = resolve_hmac_secret(hmac_secret)
    exported = 0
    tip = ""
    if privacy_cfg is None:
        try:
            from kernel.config import load_config

            privacy_cfg = load_config().values
        except Exception:
            privacy_cfg = {}

    with path.open("w", encoding="utf-8") as fh:
        for rec in decision_log.iter_from(since_id):
            from adapters.audit.privacy import maybe_redact_record
            from adapters.audit.residency import maybe_stamp_residency

            payload = maybe_redact_record(
                rec, channel="export", cfg=privacy_cfg
            )
            payload = maybe_stamp_residency(
                payload, channel="export", cfg=privacy_cfg
            )
            if secret:
                # HMAC over stable JSON without the mac field itself.
                body_obj = {k: v for k, v in payload.items() if k != "line_hmac"}
                body = json.dumps(body_obj, sort_keys=True, separators=(",", ":"))
                payload["line_hmac"] = line_hmac(body, secret)
                fh.write(json.dumps(payload, sort_keys=True) + "\n")
            else:
                fh.write(json.dumps(payload, sort_keys=True) + "\n")
            exported += 1
            tip = rec.entry_hash

    return {
        "ok": True,
        "path": str(path.resolve()),
        "exported": exported,
        "since_id": int(since_id),
        "hmac": bool(secret),
        "tip_hash": tip,
        "chain_ok": True,
    }
