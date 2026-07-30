"""
adapters/audit/object_lock.py
=============================
Optional Object Lock / compliance mirror for sealed WORM segments (ADR-022).

Default-off. Backends:
  * ``local_mirror`` — copy sealed JSONL+manifest under mirror_dir (chmod 0444)
  * ``s3_object_lock`` — soft boto3 put with Object Lock headers

Mirror failures never fail seal unless ``strict: true``.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol


class ObjectLockError(RuntimeError):
    """Object Lock / mirror operation failed."""


class S3ObjectLockClient(Protocol):
    def put_object(self, **kwargs: Any) -> Any:
        ...


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class ObjectLockConfig:
    enabled: bool = False
    backend: str = "local_mirror"  # local_mirror | s3_object_lock
    strict: bool = False
    mirror_dir: str = "data/audit_worm/object_lock_mirror"
    endpoint_url: str = ""
    bucket: str = ""
    prefix: str = "kerros/audit_worm/"
    region: str = "us-east-1"
    object_lock_mode: str = "GOVERNANCE"  # GOVERNANCE | COMPLIANCE
    retain_days: int = 365
    legal_hold: bool = False


def object_lock_config_from(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> ObjectLockConfig:
    data = dict(cfg or {})
    raw = dict(data.get("audit_object_lock") or {})

    enabled = raw.get("enabled", False)
    env = os.environ.get("KERROS_AUDIT_OBJECT_LOCK")
    if env is not None:
        enabled = _truthy(env)
    else:
        enabled = _truthy(enabled)

    backend = os.environ.get("KERROS_AUDIT_OBJECT_LOCK_BACKEND")
    if backend is None:
        backend = str(raw.get("backend") or "local_mirror")

    mirror_dir = os.environ.get("KERROS_AUDIT_OBJECT_LOCK_MIRROR_DIR")
    if mirror_dir is None:
        mirror_dir = str(raw.get("mirror_dir") or "data/audit_worm/object_lock_mirror")
    mirror_path = Path(mirror_dir)
    if not mirror_path.is_absolute() and base is not None:
        mirror_path = Path(base) / mirror_path

    endpoint = os.environ.get("KERROS_AUDIT_OBJECT_LOCK_ENDPOINT")
    if endpoint is None:
        endpoint = str(raw.get("endpoint_url") or "")

    bucket = os.environ.get("KERROS_AUDIT_OBJECT_LOCK_BUCKET")
    if bucket is None:
        bucket = str(raw.get("bucket") or "")

    prefix = os.environ.get("KERROS_AUDIT_OBJECT_LOCK_PREFIX")
    if prefix is None:
        prefix = str(raw.get("prefix") or "kerros/audit_worm/")

    retain = raw.get("retain_days", 365)
    env_r = os.environ.get("KERROS_AUDIT_OBJECT_LOCK_RETAIN_DAYS")
    if env_r is not None and str(env_r).strip().isdigit():
        retain = int(env_r)

    return ObjectLockConfig(
        enabled=bool(enabled),
        backend=str(backend or "local_mirror").strip().lower(),
        strict=_truthy(raw.get("strict", False)),
        mirror_dir=str(mirror_path),
        endpoint_url=str(endpoint or "").strip(),
        bucket=str(bucket or "").strip(),
        prefix=str(prefix or "").strip(),
        region=str(raw.get("region") or "us-east-1").strip(),
        object_lock_mode=str(raw.get("object_lock_mode") or "GOVERNANCE")
        .strip()
        .upper(),
        retain_days=max(1, int(retain)),
        legal_hold=_truthy(raw.get("legal_hold", False)),
    )


def _is_writable(path: Path) -> bool:
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return bool(mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _copy_readonly(src: Path, dest: Path) -> None:
    if dest.exists():
        raise ObjectLockError(f"refuse overwrite of sealed mirror: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    os.chmod(dest, 0o444)


def mirror_local(jsonl: Path, manifest: Path, mirror_dir: Path) -> dict[str, Any]:
    dest_jsonl = mirror_dir / jsonl.name
    dest_manifest = mirror_dir / manifest.name
    _copy_readonly(jsonl, dest_jsonl)
    _copy_readonly(manifest, dest_manifest)
    return {
        "ok": True,
        "backend": "local_mirror",
        "jsonl": str(dest_jsonl.resolve()),
        "manifest": str(dest_manifest.resolve()),
        "writable": _is_writable(dest_jsonl),
    }


def _build_boto_client(cfg: ObjectLockConfig) -> Any:
    try:
        import boto3  # type: ignore
    except ImportError as exc:
        raise ObjectLockError(
            "s3_object_lock backend requires boto3 "
            "(pip install boto3 — see requirements-optional.txt)"
        ) from exc
    kwargs: dict[str, Any] = {"region_name": cfg.region or "us-east-1"}
    if cfg.endpoint_url:
        kwargs["endpoint_url"] = cfg.endpoint_url
    return boto3.client("s3", **kwargs)


def mirror_s3(
    jsonl: Path,
    manifest: Path,
    cfg: ObjectLockConfig,
    *,
    client: Optional[S3ObjectLockClient] = None,
) -> dict[str, Any]:
    if not cfg.bucket:
        raise ObjectLockError("s3_object_lock requires bucket")
    s3 = client or _build_boto_client(cfg)
    prefix = cfg.prefix.rstrip("/") + "/" if cfg.prefix else ""
    retain_until = datetime.now(timezone.utc) + timedelta(days=cfg.retain_days)
    mode = cfg.object_lock_mode if cfg.object_lock_mode in ("GOVERNANCE", "COMPLIANCE") else "GOVERNANCE"

    put_ids: list[str] = []
    for path in (jsonl, manifest):
        key = f"{prefix}{path.name}"
        extra: dict[str, Any] = {
            "Bucket": cfg.bucket,
            "Key": key,
            "Body": path.read_bytes(),
            "ContentType": "application/json"
            if path.suffix == ".json"
            else "application/x-ndjson",
            "ObjectLockMode": mode,
            "ObjectLockRetainUntilDate": retain_until,
        }
        if cfg.legal_hold:
            extra["ObjectLockLegalHoldStatus"] = "ON"
        s3.put_object(**extra)
        put_ids.append(key)

    return {
        "ok": True,
        "backend": "s3_object_lock",
        "bucket": cfg.bucket,
        "keys": put_ids,
        "retain_until": retain_until.isoformat(),
        "mode": mode,
    }


def mirror_sealed_segment(
    jsonl_path: str | Path,
    manifest_path: str | Path,
    *,
    cfg: Optional[Mapping[str, Any]] = None,
    base: Optional[Path] = None,
    client: Optional[S3ObjectLockClient] = None,
) -> dict[str, Any]:
    """
    Mirror a sealed segment. Returns result dict; raises ObjectLockError
    only when the caller wants to handle failures (seal path uses
    ``mirror_after_seal`` which respects ``strict``).
    """
    try:
        from kernel.config import load_config

        values = dict(cfg or load_config().values)
        if base is None:
            base = load_config().base
    except Exception:
        values = dict(cfg or {})

    ol = object_lock_config_from(values, base=base)
    if not ol.enabled:
        return {"ok": True, "skipped": True, "reason": "object_lock disabled"}

    jsonl = Path(jsonl_path)
    manifest = Path(manifest_path)
    if not jsonl.is_file() or not manifest.is_file():
        raise ObjectLockError("missing sealed jsonl or manifest")

    if ol.backend == "s3_object_lock":
        return mirror_s3(jsonl, manifest, ol, client=client)
    return mirror_local(jsonl, manifest, Path(ol.mirror_dir))


def mirror_after_seal(
    seal_result: Mapping[str, Any],
    *,
    cfg: Optional[Mapping[str, Any]] = None,
    base: Optional[Path] = None,
    client: Optional[S3ObjectLockClient] = None,
) -> dict[str, Any]:
    """Best-effort post-seal mirror. Honours ``strict`` from config."""
    try:
        from kernel.config import load_config

        values = dict(cfg or load_config().values)
        if base is None:
            try:
                base = load_config().base
            except Exception:
                base = None
    except Exception:
        values = dict(cfg or {})

    ol = object_lock_config_from(values, base=base)
    if not ol.enabled:
        return {"ok": True, "skipped": True, "reason": "object_lock disabled"}

    jsonl = seal_result.get("path")
    manifest = seal_result.get("manifest")
    try:
        return mirror_sealed_segment(
            jsonl, manifest, cfg=values, base=base, client=client
        )
    except Exception as exc:
        if ol.strict:
            raise ObjectLockError(str(exc)) from exc
        return {
            "ok": False,
            "skipped": True,
            "error": str(exc),
            "strict": False,
        }
