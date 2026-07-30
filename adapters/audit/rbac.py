"""
adapters/audit/rbac.py
======================
Token → role RBAC for decision_log evidence ops (ADR-021).

Default-off. When enabled, callers present ``KERROS_AUDIT_TOKEN`` (or an
explicit token) mapped to reader | operator | admin. Does not gate
``DecisionLog.record()`` — only read/export/seal/retain/purge entrypoints.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from runtime.mesh_auth import tokens_equal

ROLES = ("reader", "operator", "admin")

# action → minimum role rank
_ROLE_RANK = {"reader": 1, "operator": 2, "admin": 3}

ACTION_MIN_ROLE: dict[str, str] = {
    "read": "reader",
    "verify": "reader",
    "export": "operator",
    "seal": "operator",
    "retain": "admin",
    "purge": "admin",
    "erasure_request": "admin",
    "erasure_review": "admin",
    "transfer_record": "admin",
    "residency": "reader",
}


class AuditRbacError(PermissionError):
    """Raised when an audit action is denied by RBAC."""


@dataclass(frozen=True)
class AuditRbac:
    enabled: bool = False
    tokens: dict[str, str] = field(default_factory=dict)  # token → role

    def role_for_token(self, token: str | None) -> str | None:
        if not token:
            return None
        provided = str(token).strip()
        if not provided:
            return None
        for expected, role in self.tokens.items():
            if tokens_equal(str(expected), provided):
                r = str(role or "").strip().lower()
                return r if r in _ROLE_RANK else None
        return None

    def check(self, action: str, token: str | None = None) -> str:
        """
        Return the resolved role if ``action`` is allowed.

        When disabled, returns ``\"open\"``. Raises ``AuditRbacError`` on deny.
        """
        act = str(action or "").strip().lower()
        if act not in ACTION_MIN_ROLE:
            raise AuditRbacError(f"unknown audit action: {action!r}")
        if not self.enabled:
            return "open"
        role = self.role_for_token(token if token is not None else current_audit_token())
        if role is None:
            raise AuditRbacError(
                f"audit RBAC: missing or invalid token for action {act!r}"
            )
        need = ACTION_MIN_ROLE[act]
        if _ROLE_RANK[role] < _ROLE_RANK[need]:
            raise AuditRbacError(
                f"audit RBAC: role {role!r} cannot perform {act!r} "
                f"(requires {need!r})"
            )
        return role


def current_audit_token() -> str:
    return str(os.environ.get("KERROS_AUDIT_TOKEN") or "").strip()


def _parse_token_map(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {
            str(k).strip(): str(v).strip().lower()
            for k, v in raw.items()
            if str(k).strip() and str(v).strip()
        }
    text = str(raw).strip()
    if not text:
        return {}
    out: dict[str, str] = {}
    for part in text.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        tok, _, role = part.partition("=")
        tok, role = tok.strip(), role.strip().lower()
        if tok and role:
            out[tok] = role
    return out


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def audit_rbac_from_config(cfg: Optional[Mapping[str, Any]] = None) -> AuditRbac:
    data = dict(cfg or {})
    raw = dict(data.get("audit_rbac") or {})
    enabled = raw.get("enabled", False)
    env = os.environ.get("KERROS_AUDIT_RBAC")
    if env is not None:
        enabled = _truthy(env)
    else:
        enabled = _truthy(enabled)

    tokens = _parse_token_map(raw.get("tokens"))
    env_tokens = os.environ.get("KERROS_AUDIT_RBAC_TOKENS")
    if env_tokens:
        tokens = _parse_token_map(env_tokens)
    return AuditRbac(enabled=bool(enabled), tokens=tokens)


def require_audit_action(
    action: str,
    *,
    token: str | None = None,
    cfg: Optional[Mapping[str, Any]] = None,
) -> str:
    """Load RBAC from cfg (or defaults) and check ``action``."""
    try:
        if cfg is None:
            from kernel.config import load_config

            values = load_config().values
        else:
            values = dict(cfg)
    except Exception:
        values = dict(cfg or {})
    return audit_rbac_from_config(values).check(action, token=token)
