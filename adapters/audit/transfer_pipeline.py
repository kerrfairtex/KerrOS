"""
adapters/audit/transfer_pipeline.py
===================================
Execute transfer-*intent* rows by copying evidence (ADR-027).

Default-off. Backends:
  * ``local_copy`` — copy sealed WORM segment and/or export JSONL under dest_dir
  * ``http_put`` — soft HTTP PUT of a single payload file (urllib; no hard deps)

Never rewrites sealed WORM sources — only copies. Hardware WORM / IdP still
deferred.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from adapters.audit.transfer_ledger import TransferLedger, transfer_config_from
from adapters.audit.worm_store import WormStore


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class TransferPipelineConfig:
    enabled: bool = False  # parent audit_transfers.enabled
    execute_enabled: bool = False
    backend: str = "local_copy"  # local_copy | http_put
    dest_dir: str = "data/transfer_outbox"
    http_url: str = ""
    http_token: str = ""
    http_timeout_s: float = 5.0
    sources: list[str] = None  # type: ignore[assignment]
    worm_dir: str = "data/audit_worm"
    db_path: str = "data/transfer_requests.db"

    def __post_init__(self) -> None:
        if self.sources is None:
            self.sources = ["sealed_segments"]


def pipeline_config_from(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> TransferPipelineConfig:
    data = dict(cfg or {})
    raw = dict(data.get("audit_transfers") or {})
    retention = dict(data.get("audit_retention") or {})
    base_cfg = transfer_config_from(data, base=base)

    execute = raw.get("execute_enabled", False)
    env_e = os.environ.get("KERROS_AUDIT_TRANSFER_EXECUTE")
    if env_e is not None:
        execute = _truthy(env_e)
    else:
        execute = _truthy(execute)

    backend = os.environ.get("KERROS_AUDIT_TRANSFER_BACKEND")
    if backend is None:
        backend = str(raw.get("backend") or "local_copy")

    dest = os.environ.get("KERROS_AUDIT_TRANSFER_DEST")
    if dest is None:
        dest = str(raw.get("dest_dir") or "data/transfer_outbox")

    http_url = os.environ.get("KERROS_AUDIT_TRANSFER_HTTP_URL")
    if http_url is None:
        http_url = str(raw.get("http_url") or "")

    http_token = os.environ.get("KERROS_AUDIT_TRANSFER_HTTP_TOKEN")
    if http_token is None:
        http_token = str(raw.get("http_token") or "")

    sources_raw = raw.get("sources") or ["sealed_segments"]
    if isinstance(sources_raw, str):
        sources = [s.strip() for s in sources_raw.split(",") if s.strip()]
    else:
        sources = [str(s).strip() for s in sources_raw if str(s).strip()]

    worm_dir = str(
        raw.get("worm_dir")
        or retention.get("worm_dir")
        or "data/audit_worm"
    )
    env_w = os.environ.get("KERROS_AUDIT_WORM_DIR")
    if env_w:
        worm_dir = env_w

    dest_path = Path(dest)
    worm_path = Path(worm_dir)
    if base is not None:
        if not dest_path.is_absolute():
            dest_path = Path(base) / dest_path
        if not worm_path.is_absolute():
            worm_path = Path(base) / worm_path

    return TransferPipelineConfig(
        enabled=base_cfg.enabled,
        execute_enabled=bool(execute),
        backend=str(backend or "local_copy").strip().lower(),
        dest_dir=str(dest_path),
        http_url=str(http_url or "").strip(),
        http_token=str(http_token or "").strip(),
        http_timeout_s=max(0.5, float(raw.get("http_timeout_s") or 5.0)),
        sources=sources or ["sealed_segments"],
        worm_dir=str(worm_path),
        db_path=base_cfg.db_path,
    )


def _copy_sealed_segments(
    worm: WormStore, dest: Path, *, segment_ids: Optional[Sequence[int]] = None
) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    segs = worm.list_segments()
    if segment_ids:
        wanted = {int(s) for s in segment_ids}
        segs = [s for s in segs if int(s.get("segment") or 0) in wanted]
    for seg in segs:
        num = int(seg.get("segment") or 0)
        jsonl, manifest = worm.segment_paths(num)
        if not jsonl.is_file() or not manifest.is_file():
            continue
        for src in (jsonl, manifest):
            target = dest / src.name
            if target.exists():
                continue
            shutil.copy2(src, target)
            # Keep copies writable in outbox (sources stay 0444).
            try:
                os.chmod(target, 0o644)
            except OSError:
                pass
            copied.append(str(target))
    return copied


def _export_jsonl(dest: Path, *, log_db: Optional[Path] = None) -> list[str]:
    from adapters.audit.decision_log_export import export_decision_log_jsonl
    from kernel.decision_log import DecisionLog

    dest.mkdir(parents=True, exist_ok=True)
    out_path = dest / "decision_log_export.jsonl"
    log = DecisionLog(log_db) if log_db is not None else DecisionLog()
    result = export_decision_log_jsonl(out_path, log=log, skip_rbac=True)
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "export failed")
    return [str(out_path)]


def _http_put(url: str, path: Path, *, token: str = "", timeout_s: float = 5.0) -> None:
    data = path.read_bytes()
    headers = {"Content-Type": "application/octet-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        resp.read(256)


class TransferPipelineError(RuntimeError):
    pass


def execute_transfer(
    request_id: int,
    *,
    cfg: Optional[Mapping[str, Any]] = None,
    base: Optional[Path] = None,
    decision_log_db: Optional[Path] = None,
    segment_ids: Optional[Sequence[int]] = None,
    audit_token: Optional[str] = None,
    skip_rbac: bool = False,
) -> dict[str, Any]:
    """
    Execute a recorded transfer intent: copy evidence to outbox / HTTP PUT.

    Source sealed segments are never mutated. Ledger status becomes
    ``executed`` or ``failed``.
    """
    if not skip_rbac:
        from adapters.audit.rbac import require_audit_action

        require_audit_action("transfer_execute", token=audit_token, cfg=cfg)

    pcfg = pipeline_config_from(cfg, base=base)
    if not pcfg.enabled:
        return {"ok": False, "error": "audit_transfers disabled", "enabled": False}
    if not pcfg.execute_enabled:
        return {
            "ok": False,
            "error": "transfer execute disabled (set execute_enabled / KERROS_AUDIT_TRANSFER_EXECUTE)",
            "enabled": True,
            "execute_enabled": False,
        }

    ledger = TransferLedger(pcfg.db_path)
    try:
        intent = ledger.get(int(request_id))
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}

    if str(intent.get("status") or "") == "executed":
        return {
            "ok": False,
            "error": f"transfer #{request_id} already executed",
            "transfer": intent,
        }

    run_dir = (
        Path(pcfg.dest_dir)
        / str(intent.get("to_region") or "unknown")
        / f"transfer-{int(request_id)}"
    )
    artifacts: list[str] = []
    meta: dict[str, Any] = {
        "request_id": int(request_id),
        "backend": pcfg.backend,
        "sources": list(pcfg.sources),
        "intent": intent,
    }

    try:
        worm = WormStore(pcfg.worm_dir)
        if "sealed_segments" in pcfg.sources:
            artifacts.extend(
                _copy_sealed_segments(worm, run_dir, segment_ids=segment_ids)
            )
        if "export_jsonl" in pcfg.sources:
            artifacts.extend(_export_jsonl(run_dir, log_db=decision_log_db))

        if not artifacts:
            raise TransferPipelineError(
                "no artifacts produced — seal segments and/or enable export_jsonl source"
            )

        if pcfg.backend == "http_put":
            if not pcfg.http_url:
                raise TransferPipelineError("http_put requires http_url")
            # PUT first artifact (foundation); operators can loop externally.
            _http_put(
                pcfg.http_url,
                Path(artifacts[0]),
                token=pcfg.http_token,
                timeout_s=pcfg.http_timeout_s,
            )
            meta["http_url"] = pcfg.http_url
            meta["http_put_file"] = artifacts[0]
        elif pcfg.backend != "local_copy":
            raise TransferPipelineError(f"unknown backend: {pcfg.backend!r}")

        manifest = {
            "transfer_id": int(request_id),
            "executed_at": time.time(),
            "from_region": intent.get("from_region"),
            "to_region": intent.get("to_region"),
            "mechanism": intent.get("mechanism"),
            "artifacts": artifacts,
            "backend": pcfg.backend,
        }
        man_path = run_dir / "transfer_manifest.json"
        run_dir.mkdir(parents=True, exist_ok=True)
        man_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts.append(str(man_path))

        updated = ledger.mark_status(
            int(request_id),
            "executed",
            notes=f"executed via {pcfg.backend}; artifacts={len(artifacts)}",
        )
        return {
            "ok": True,
            "transfer": updated,
            "artifacts": artifacts,
            "dest_dir": str(run_dir),
            "backend": pcfg.backend,
            "worm_untouched": True,
            "policy": "transfer_executed_copy_only",
            **meta,
        }
    except Exception as exc:
        try:
            ledger.mark_status(
                int(request_id),
                "failed",
                notes=f"execute failed: {exc}",
            )
        except Exception:
            pass
        return {
            "ok": False,
            "error": str(exc),
            "artifacts": artifacts,
            "dest_dir": str(run_dir),
            "worm_untouched": True,
        }
