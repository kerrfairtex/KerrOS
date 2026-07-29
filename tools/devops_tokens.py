"""
tools/devops_tokens.py
===========================
Least-privilege DevOps token checks (P4 / README §6–§7).

One dedicated env per vendor — never share a single mega-token across
GitHub/Vercel/Netlify/Railway/Cloudflare/Stripe/Supabase. Shape checks
reject obvious over-privilege (e.g. Stripe live secret keys). Scope_gate
still owns arm/disarm; this module only validates credential *shape* and
presence before deploy CLIs run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ServiceCredentialSpec:
    """Declarative per-service credential expectations."""

    name: str
    env_vars: tuple[str, ...]  # first present wins (aliases)
    required: bool = True
    # If set, token must start with one of these (case-sensitive).
    allow_prefixes: tuple[str, ...] = ()
    # Hard-fail if token starts with any of these.
    forbid_prefixes: tuple[str, ...] = ()
    # Soft warnings when these envs are set (over-privileged for agent use).
    warn_if_set: tuple[str, ...] = ()
    notes: str = ""


# Canonical 8-tool DevOps pipeline (matches config/capabilities/devops_tools.yaml).
SERVICE_SPECS: dict[str, ServiceCredentialSpec] = {
    "github": ServiceCredentialSpec(
        name="github",
        env_vars=("GITHUB_TOKEN",),
        notes=(
            "Fine-grained PAT: contents/metadata write for one repo; "
            "or classic `repo` only — no admin:org / delete_repo."
        ),
    ),
    "supabase": ServiceCredentialSpec(
        name="supabase",
        env_vars=("SUPABASE_ACCESS_TOKEN",),
        required=False,  # CLI may already be logged in
        warn_if_set=("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"),
        notes=(
            "Prefer SUPABASE_ACCESS_TOKEN (Management API / CLI). "
            "Do not put service-role keys in agent .env for routine migrate."
        ),
    ),
    "vercel": ServiceCredentialSpec(
        name="vercel",
        env_vars=("VERCEL_TOKEN",),
        notes="Token scoped to one team/project; bind VERCEL_ORG_ID / VERCEL_PROJECT_ID.",
    ),
    "netlify": ServiceCredentialSpec(
        name="netlify",
        env_vars=("NETLIFY_AUTH_TOKEN", "NETLIFTY_API_KEY"),  # legacy typo alias
        notes="Personal access token scoped to the target site/team.",
    ),
    "railway": ServiceCredentialSpec(
        name="railway",
        env_vars=("RAILWAY_API_KEY",),
        notes="Project-scoped API token — not account-wide admin if avoidable.",
    ),
    "cloudflare": ServiceCredentialSpec(
        name="cloudflare",
        env_vars=("CLOUDFLARE_API_TOKEN",),
        notes=(
            "API Token: Workers Scripts Edit (+ DNS Edit if needed) on one "
            "account/zone; set CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_ZONE_ID."
        ),
    ),
    "stripe": ServiceCredentialSpec(
        name="stripe",
        env_vars=("STRIPE_API_KEY", "STRIPE_SECRET_KEY"),
        allow_prefixes=("sk_test_", "rk_test_"),
        forbid_prefixes=("sk_live_", "rk_live_"),
        notes="Test-mode secret or restricted keys only — never sk_live_ in KerrOS agents.",
    ),
}

# Map router/capability tool names → service credential keys.
TOOL_SERVICE: dict[str, str] = {
    "github_create_repo": "github",
    "github_push": "github",
    "supabase_migrate": "supabase",
    "vercel_deploy": "vercel",
    "netlify_deploy": "netlify",
    "railway_deploy": "railway",
    "cloudflare_deploy": "cloudflare",
    "stripe_trigger": "stripe",
}


@dataclass
class CredentialCheck:
    service: str
    ok: bool
    message: str
    warnings: list[str] = field(default_factory=list)
    env_used: Optional[str] = None
    present: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "ok": self.ok,
            "message": self.message,
            "warnings": list(self.warnings),
            "env_used": self.env_used,
            "present": self.present,
        }


def _resolve_env(
    names: tuple[str, ...],
    environ: Optional[dict[str, str]] = None,
) -> tuple[Optional[str], str]:
    source = environ if environ is not None else os.environ
    for name in names:
        value = (source.get(name) or "").strip()
        if value:
            return name, value
    return None, ""


def check_service(
    service: str,
    *,
    environ: Optional[dict[str, str]] = None,
) -> CredentialCheck:
    """Validate credential shape/presence for one DevOps service.

    ``environ`` if provided is used instead of ``os.environ`` (for tests).
    """
    spec = SERVICE_SPECS.get(service)
    if spec is None:
        return CredentialCheck(
            service=service,
            ok=False,
            message=f"unknown deploy service '{service}'",
        )
    return _check_spec(spec, environ)


def _check_spec(
    spec: ServiceCredentialSpec,
    environ: Optional[dict[str, str]] = None,
) -> CredentialCheck:
    source = environ if environ is not None else os.environ
    warnings: list[str] = []
    for warn_env in spec.warn_if_set:
        if (source.get(warn_env) or "").strip():
            warnings.append(
                f"{warn_env} is set — prefer least-privilege tokens "
                f"(see docs/DEVOPS_TOKEN_SCOPING.md); avoid in agent .env"
            )

    env_name, value = _resolve_env(spec.env_vars, environ)
    if not value:
        if spec.required:
            aliases = " / ".join(spec.env_vars)
            return CredentialCheck(
                service=spec.name,
                ok=False,
                present=False,
                message=f"missing {aliases} — use a dedicated least-privilege token",
                warnings=warnings,
            )
        return CredentialCheck(
            service=spec.name,
            ok=True,
            present=False,
            message="no token in env (CLI login may still work)",
            warnings=warnings,
        )

    for prefix in spec.forbid_prefixes:
        if value.startswith(prefix):
            return CredentialCheck(
                service=spec.name,
                ok=False,
                present=True,
                env_used=env_name,
                message=(
                    f"{env_name} looks over-privileged ({prefix}…); "
                    f"refusing — {spec.notes}"
                ),
                warnings=warnings,
            )

    if spec.allow_prefixes and not any(value.startswith(p) for p in spec.allow_prefixes):
        allowed = ", ".join(spec.allow_prefixes)
        return CredentialCheck(
            service=spec.name,
            ok=False,
            present=True,
            env_used=env_name,
            message=(
                f"{env_name} must start with one of [{allowed}] "
                f"(got different prefix); {spec.notes}"
            ),
            warnings=warnings,
        )

    return CredentialCheck(
        service=spec.name,
        ok=True,
        present=True,
        env_used=env_name,
        message=f"{env_name} present",
        warnings=warnings,
    )


def check_tool(tool_name: str, **kwargs: Any) -> CredentialCheck:
    service = TOOL_SERVICE.get(tool_name)
    if not service:
        return CredentialCheck(
            service=tool_name,
            ok=False,
            message=f"no credential mapping for tool '{tool_name}'",
        )
    return check_service(service, **kwargs)


def preflight(tool_or_service: str, **kwargs: Any) -> Optional[str]:
    """Return an error string if credentials block the deploy tool, else None.

    Accepts either a router tool name (e.g. ``stripe_trigger``) or a service
    key (e.g. ``stripe``).
    """
    if tool_or_service in TOOL_SERVICE:
        result = check_tool(tool_or_service, **kwargs)
    else:
        result = check_service(tool_or_service, **kwargs)
    if result.ok:
        return None
    return f"[deploy credentials:{result.service}] {result.message}"


def audit_all(*, environ: Optional[dict[str, str]] = None) -> list[CredentialCheck]:
    return [check_service(name, environ=environ) for name in SERVICE_SPECS]


def summary_table(checks: Optional[list[CredentialCheck]] = None) -> str:
    rows = checks if checks is not None else audit_all()
    lines = ["service     status   env                  notes"]
    lines.append("-" * 72)
    for c in rows:
        status = "OK" if c.ok else "FAIL"
        env = c.env_used or ("(missing)" if c.present is False else "?")
        note = c.message if not c.ok else ("; ".join(c.warnings) if c.warnings else c.message)
        lines.append(f"{c.service:<10}  {status:<6}  {env:<20}  {note[:40]}")
    return "\n".join(lines)
