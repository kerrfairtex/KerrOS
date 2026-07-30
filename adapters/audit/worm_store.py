"""
adapters/audit/worm_store.py
============================
Software-WORM sealed JSONL segments for the decision log (ADR-019).

Not a hardware WORM appliance — sealed files are chmod 0444 with a
manifest; rewrite of sealed paths is refused by this API.
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Any, Optional, Union

from adapters.audit.decision_log_export import (
    line_hmac,
    record_dict,
    resolve_hmac_secret,
)
from kernel.decision_log import DecisionLog, GENESIS_HASH, compute_entry_hash, canonical_payload


class WormStoreError(RuntimeError):
    """WORM store operation refused or failed."""


def _is_writable(path: Path) -> bool:
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return bool(mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


class WormStore:
    """Cold sealed JSONL segments under ``root/segments/``."""

    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)
        self.segments_dir = self.root / "segments"
        self.segments_dir.mkdir(parents=True, exist_ok=True)

    def list_segments(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for manifest in sorted(self.segments_dir.glob("*.manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                data = dict(data)
                data.setdefault("manifest", str(manifest))
                out.append(data)
        out.sort(key=lambda d: int(d.get("segment", 0)))
        return out

    def has_sealed_segments(self) -> bool:
        return bool(self.list_segments())

    def next_segment_number(self) -> int:
        nums = [int(d.get("segment", 0)) for d in self.list_segments()]
        return (max(nums) + 1) if nums else 1

    def last_sealed_tip(self) -> str:
        segs = self.list_segments()
        if not segs:
            return GENESIS_HASH
        return str(segs[-1].get("tip_hash") or GENESIS_HASH)

    def segment_paths(self, segment: int) -> tuple[Path, Path]:
        stem = f"{int(segment):06d}"
        return (
            self.segments_dir / f"{stem}.jsonl",
            self.segments_dir / f"{stem}.manifest.json",
        )

    def seal_from_log(
        self,
        log: DecisionLog,
        *,
        through_id: int,
        hmac_secret: Optional[str] = None,
        segment: Optional[int] = None,
        audit_token: Optional[str] = None,
        skip_rbac: bool = False,
    ) -> dict[str, Any]:
        """
        Seal records with id <= through_id into a new read-only JSONL segment.
        """
        if not skip_rbac:
            from adapters.audit.rbac import require_audit_action

            require_audit_action("seal", token=audit_token)
        through_id = int(through_id)
        if through_id < 1:
            raise WormStoreError("through_id must be >= 1")

        chain = log.verify_chain()
        if not chain.get("ok"):
            raise WormStoreError(f"hot chain invalid: {chain.get('error')}")

        records = list(log.iter_through(through_id))
        if not records:
            raise WormStoreError(f"no records with id <= {through_id}")
        if records[-1].id != through_id:
            raise WormStoreError(
                f"through_id {through_id} not present (last={records[-1].id})"
            )

        seg_no = int(segment) if segment is not None else self.next_segment_number()
        jsonl_path, manifest_path = self.segment_paths(seg_no)
        if jsonl_path.exists() or manifest_path.exists():
            raise WormStoreError(f"segment {seg_no:06d} already exists — refuse rewrite")

        secret = resolve_hmac_secret(hmac_secret)
        tip = ""
        first_id = records[0].id
        last_id = records[-1].id
        prev_tip = records[0].prev_hash or GENESIS_HASH

        # Write privately then chmod.
        tmp = jsonl_path.with_suffix(".jsonl.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                for rec in records:
                    payload = record_dict(rec)
                    if secret:
                        body = json.dumps(
                            payload, sort_keys=True, separators=(",", ":")
                        )
                        payload["line_hmac"] = line_hmac(body, secret)
                    fh.write(json.dumps(payload, sort_keys=True) + "\n")
                    tip = rec.entry_hash
            os.replace(tmp, jsonl_path)
            os.chmod(jsonl_path, 0o444)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

        manifest = {
            "segment": seg_no,
            "first_id": first_id,
            "last_id": last_id,
            "row_count": len(records),
            "prev_tip": prev_tip,
            "tip_hash": tip,
            "sealed_at": time.time(),
            "jsonl": jsonl_path.name,
            "hmac": bool(secret),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(manifest_path, 0o444)

        verify = self.verify_segment(seg_no, hmac_secret=secret or None)
        if not verify.get("ok"):
            raise WormStoreError(f"sealed segment failed verify: {verify}")

        result = {
            "ok": True,
            "segment": seg_no,
            "path": str(jsonl_path.resolve()),
            "manifest": str(manifest_path.resolve()),
            "first_id": first_id,
            "last_id": last_id,
            "row_count": len(records),
            "tip_hash": tip,
            "writable": _is_writable(jsonl_path),
        }
        try:
            from adapters.audit.siem_forwarder import get_siem_forwarder

            get_siem_forwarder().forward_seal(
                {
                    "segment": seg_no,
                    "first_id": first_id,
                    "last_id": last_id,
                    "row_count": len(records),
                    "tip_hash": tip,
                }
            )
        except Exception:
            pass
        return result

    def verify_segment(
        self,
        segment: int,
        *,
        hmac_secret: Optional[str] = None,
    ) -> dict[str, Any]:
        jsonl_path, manifest_path = self.segment_paths(int(segment))
        if not jsonl_path.is_file() or not manifest_path.is_file():
            return {"ok": False, "error": "missing segment or manifest"}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"manifest unreadable: {exc}"}

        secret = resolve_hmac_secret(hmac_secret)
        expected_prev: str | None = None
        tip = ""
        count = 0
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                count += 1
                try:
                    obj = json.loads(line)
                except Exception as exc:
                    return {"ok": False, "error": f"bad json line {count}: {exc}"}
                if secret:
                    mac = obj.pop("line_hmac", None)
                    body = json.dumps(obj, sort_keys=True, separators=(",", ":"))
                    if not mac or mac != line_hmac(body, secret):
                        return {
                            "ok": False,
                            "error": f"line_hmac mismatch at line {count}",
                        }
                prev = str(obj.get("prev_hash") or GENESIS_HASH)
                if expected_prev is not None and prev != expected_prev:
                    return {
                        "ok": False,
                        "error": f"prev_hash mismatch at line {count}",
                    }
                payload = canonical_payload(
                    float(obj["timestamp"]),
                    str(obj["actor"]),
                    str(obj["decision_type"]),
                    str(obj["input_summary"]),
                    str(obj["outcome"]),
                    str(obj.get("reason") or ""),
                )
                expected = compute_entry_hash(prev, payload)
                actual = str(obj.get("entry_hash") or "")
                if actual != expected:
                    return {
                        "ok": False,
                        "error": f"entry_hash mismatch at line {count}",
                    }
                expected_prev = actual
                tip = actual

        if count != int(manifest.get("row_count", -1)):
            return {
                "ok": False,
                "error": "row_count mismatch",
                "manifest_rows": manifest.get("row_count"),
                "file_rows": count,
            }
        if tip != str(manifest.get("tip_hash") or ""):
            return {
                "ok": False,
                "error": "tip_hash mismatch",
                "manifest_tip": manifest.get("tip_hash"),
                "file_tip": tip,
            }
        if _is_writable(jsonl_path):
            return {"ok": False, "error": "segment file is still writable"}
        return {
            "ok": True,
            "segment": int(segment),
            "row_count": count,
            "tip_hash": tip,
            "writable": False,
        }
