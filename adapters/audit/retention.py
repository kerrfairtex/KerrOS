"""
adapters/audit/retention.py
===========================
Retention policy for the hot decision_log (ADR-019).

Default-off. ``archive`` seals an aged id prefix to software-WORM then
prefix-deletes from SQLite. ``purge`` deletes without sealing and is
refused when sealed segments exist unless ``allow_purge`` is set.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from adapters.audit.worm_store import WormStore, WormStoreError
from kernel.decision_log import DecisionLog


DEFAULT_RETENTION: dict[str, Any] = {
    "enabled": False,
    "retain_days": 90,
    "action": "archive",  # archive | purge
    "worm_dir": "data/audit_worm",
    "allow_purge": False,
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def retention_config_from(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> dict[str, Any]:
    data = dict(DEFAULT_RETENTION)
    raw = dict((cfg or {}).get("audit_retention") or {})
    data.update(raw)

    env_enabled = os.environ.get("KERROS_AUDIT_RETENTION")
    if env_enabled is not None:
        data["enabled"] = _truthy(env_enabled)
    env_days = os.environ.get("KERROS_AUDIT_RETAIN_DAYS")
    if env_days is not None and str(env_days).strip().isdigit():
        data["retain_days"] = int(env_days)
    env_action = os.environ.get("KERROS_AUDIT_RETENTION_ACTION")
    if env_action:
        data["action"] = env_action.strip().lower()
    env_dir = os.environ.get("KERROS_AUDIT_WORM_DIR")
    if env_dir:
        data["worm_dir"] = env_dir

    worm_dir = Path(str(data.get("worm_dir") or "data/audit_worm"))
    if not worm_dir.is_absolute() and base is not None:
        worm_dir = Path(base) / worm_dir
    data["worm_dir"] = str(worm_dir)
    data["enabled"] = _truthy(data.get("enabled", False))
    data["allow_purge"] = _truthy(data.get("allow_purge", False))
    data["retain_days"] = max(0, int(data.get("retain_days") or 0))
    data["action"] = str(data.get("action") or "archive").strip().lower()
    return data


def apply_retention(
    log: DecisionLog,
    *,
    cfg: Optional[Mapping[str, Any]] = None,
    now: Optional[float] = None,
    base: Optional[Path] = None,
    hmac_secret: Optional[str] = None,
) -> dict[str, Any]:
    """
    Apply retention once. Returns a result dict (ok / noop / error).
    """
    policy = retention_config_from(cfg, base=base)
    if not policy["enabled"]:
        return {"ok": True, "action": "noop", "reason": "retention disabled"}

    action = policy["action"]
    if action not in ("archive", "purge"):
        return {"ok": False, "error": f"unknown action {action!r}"}

    cutoff = float(now if now is not None else time.time()) - (
        policy["retain_days"] * 86400.0
    )
    through_id = log.retention_cutoff_id(cutoff)
    if through_id is None:
        return {
            "ok": True,
            "action": "noop",
            "reason": "no aged rows",
            "cutoff_ts": cutoff,
        }

    worm = WormStore(policy["worm_dir"])

    if action == "purge":
        if not policy["allow_purge"]:
            return {
                "ok": False,
                "error": "purge refused (allow_purge=false); use action=archive",
            }
        if worm.has_sealed_segments():
            return {
                "ok": False,
                "error": "purge refused while sealed WORM segments exist "
                "(archive is the LGU-safe path)",
            }
        deleted = log.delete_through(through_id, _retention=True)
        try:
            log.record(
                "retention",
                "retention_apply",
                f"through_id:{through_id}",
                "purged",
                f"deleted:{deleted}",
            )
        except Exception:
            pass
        return {
            "ok": True,
            "action": "purge",
            "through_id": through_id,
            "deleted": deleted,
            "cutoff_ts": cutoff,
        }

    # archive
    try:
        sealed = worm.seal_from_log(
            log, through_id=through_id, hmac_secret=hmac_secret
        )
    except WormStoreError as exc:
        return {"ok": False, "error": str(exc), "action": "archive"}

    deleted = log.delete_through(through_id, _retention=True)
    chain = log.verify_chain()
    try:
        log.record(
            "retention",
            "retention_apply",
            f"through_id:{through_id};segment:{sealed.get('segment')}",
            "archived",
            f"deleted:{deleted}",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "action": "archive",
        "through_id": through_id,
        "deleted": deleted,
        "cutoff_ts": cutoff,
        "segment": sealed,
        "hot_chain_ok": bool(chain.get("ok")),
    }
