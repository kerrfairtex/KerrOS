"""
adapters/audit/privacy.py
=========================
Jurisdiction privacy foundation for decision_log egress (ADR-024).

Default-off. Redacts or hashes configured fields on **egress only**
(export / SIEM / CLI read). Never mutates SQLite rows or sealed WORM
segments — rewriting stored fields would break the hash chain (ADR-017).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Union

from kernel.decision_log import DecisionRecord

DEFAULT_FIELDS: tuple[str, ...] = ("input_summary", "reason", "actor")
DEFAULT_CHANNELS: tuple[str, ...] = ("export", "siem", "cli_read")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class AuditPrivacyConfig:
    enabled: bool = False
    mode: str = "hash"  # hash | redact
    fields: list[str] = field(default_factory=lambda: list(DEFAULT_FIELDS))
    apply_on: list[str] = field(default_factory=lambda: list(DEFAULT_CHANNELS))
    salt: str = ""


def privacy_config_from(
    cfg: Optional[Mapping[str, Any]] = None,
) -> AuditPrivacyConfig:
    data = dict(cfg or {})
    raw = dict(data.get("audit_privacy") or {})

    enabled = raw.get("enabled", False)
    env = os.environ.get("KERROS_AUDIT_PRIVACY")
    if env is not None:
        enabled = _truthy(env)
    else:
        enabled = _truthy(enabled)

    mode = os.environ.get("KERROS_AUDIT_PRIVACY_MODE")
    if mode is None:
        mode = str(raw.get("mode") or "hash")
    mode = str(mode or "hash").strip().lower()
    if mode not in ("hash", "redact"):
        mode = "hash"

    fields_env = os.environ.get("KERROS_AUDIT_PRIVACY_FIELDS")
    if fields_env is not None:
        fields = [f.strip() for f in fields_env.split(",") if f.strip()]
    else:
        raw_fields = raw.get("fields")
        if isinstance(raw_fields, (list, tuple)):
            fields = [str(f).strip() for f in raw_fields if str(f).strip()]
        else:
            fields = list(DEFAULT_FIELDS)

    apply_env = os.environ.get("KERROS_AUDIT_PRIVACY_APPLY_ON")
    if apply_env is not None:
        apply_on = [c.strip() for c in apply_env.split(",") if c.strip()]
    else:
        raw_on = raw.get("apply_on")
        if isinstance(raw_on, (list, tuple)):
            apply_on = [str(c).strip() for c in raw_on if str(c).strip()]
        else:
            apply_on = list(DEFAULT_CHANNELS)

    salt = os.environ.get("KERROS_AUDIT_PRIVACY_SALT")
    if salt is None:
        salt = str(raw.get("salt") or "")

    return AuditPrivacyConfig(
        enabled=bool(enabled),
        mode=mode,
        fields=fields or list(DEFAULT_FIELDS),
        apply_on=apply_on or list(DEFAULT_CHANNELS),
        salt=str(salt or ""),
    )


def _hash_value(value: Any, salt: str) -> str:
    text = "" if value is None else str(value)
    digest = hashlib.sha256(f"{salt}|{text}".encode("utf-8")).hexdigest()
    return f"hash:{digest[:16]}"


def _transform_field(value: Any, *, mode: str, salt: str) -> Any:
    if mode == "redact":
        return "[REDACTED]"
    return _hash_value(value, salt)


def maybe_redact_mapping(
    payload: Mapping[str, Any],
    *,
    channel: str,
    cfg: Optional[Union[AuditPrivacyConfig, Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Return a copy of ``payload`` with privacy transforms applied when enabled
    for ``channel``. Unknown channels are treated as no-op unless listed in
    ``apply_on``.
    """
    if isinstance(cfg, AuditPrivacyConfig):
        privacy = cfg
    elif isinstance(cfg, Mapping):
        privacy = privacy_config_from(cfg)
    else:
        try:
            from kernel.config import load_config

            privacy = privacy_config_from(load_config().values)
        except Exception:
            privacy = AuditPrivacyConfig()

    out = dict(payload)
    if not privacy.enabled:
        return out
    if str(channel or "").strip() not in privacy.apply_on:
        return out

    for key in privacy.fields:
        if key in out:
            out[key] = _transform_field(
                out.get(key), mode=privacy.mode, salt=privacy.salt
            )
    out["privacy"] = {
        "applied": True,
        "mode": privacy.mode,
        "channel": channel,
        "fields": list(privacy.fields),
    }
    return out


def maybe_redact_record(
    rec: DecisionRecord,
    *,
    channel: str,
    cfg: Optional[Union[AuditPrivacyConfig, Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    from adapters.audit.decision_log_export import record_dict

    return maybe_redact_mapping(record_dict(rec), channel=channel, cfg=cfg)


def privacy_status(
    cfg: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    privacy = privacy_config_from(cfg)
    return {
        "enabled": privacy.enabled,
        "mode": privacy.mode,
        "fields": list(privacy.fields),
        "apply_on": list(privacy.apply_on),
        "salt_configured": bool(privacy.salt),
    }
