"""
adapters/audit/residency.py
===========================
Data residency stamp for decision_log egress (ADR-025).

Default-off. When enabled, stamps ``residency_region`` onto egress payloads
(export / SIEM / CLI). Never mutates SQLite hash-chain fields or sealed WORM.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class AuditResidencyConfig:
    enabled: bool = False
    region: str = ""
    stamp_on_export: bool = True
    stamp_on_siem: bool = True
    stamp_on_cli_read: bool = True


def residency_config_from(
    cfg: Optional[Mapping[str, Any]] = None,
) -> AuditResidencyConfig:
    data = dict(cfg or {})
    raw = dict(data.get("audit_residency") or {})

    enabled = raw.get("enabled", False)
    env = os.environ.get("KERROS_AUDIT_RESIDENCY")
    if env is not None:
        enabled = _truthy(env)
    else:
        enabled = _truthy(enabled)

    region = os.environ.get("KERROS_AUDIT_RESIDENCY_REGION")
    if region is None:
        region = str(raw.get("region") or "")

    return AuditResidencyConfig(
        enabled=bool(enabled),
        region=str(region or "").strip(),
        stamp_on_export=_truthy(raw.get("stamp_on_export", True)),
        stamp_on_siem=_truthy(raw.get("stamp_on_siem", True)),
        stamp_on_cli_read=_truthy(raw.get("stamp_on_cli_read", True)),
    )


def maybe_stamp_residency(
    payload: Mapping[str, Any],
    *,
    channel: str,
    cfg: Optional[Union[AuditResidencyConfig, Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    if isinstance(cfg, AuditResidencyConfig):
        residency = cfg
    elif isinstance(cfg, Mapping):
        residency = residency_config_from(cfg)
    else:
        try:
            from kernel.config import load_config

            residency = residency_config_from(load_config().values)
        except Exception:
            residency = AuditResidencyConfig()

    out = dict(payload)
    if not residency.enabled or not residency.region:
        return out

    channel = str(channel or "").strip()
    allow = {
        "export": residency.stamp_on_export,
        "siem": residency.stamp_on_siem,
        "cli_read": residency.stamp_on_cli_read,
    }.get(channel, False)
    if not allow:
        return out

    out["residency_region"] = residency.region
    return out


def residency_status(
    cfg: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    r = residency_config_from(cfg)
    return {
        "enabled": r.enabled,
        "region": r.region,
        "stamp_on_export": r.stamp_on_export,
        "stamp_on_siem": r.stamp_on_siem,
        "stamp_on_cli_read": r.stamp_on_cli_read,
    }
