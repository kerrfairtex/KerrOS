"""
tools/scope_gate.py
====================
Fail-closed authorization gate for active/offensive tools.

Policy (tool classes, arm defaults, messages) loads from
`config/scope_policy.yaml`. Runtime allowlists (targets/CIDRs/arm window)
remain in `config/scope.json`.

Any tool that touches a real network target must pass through is_authorized()
before it runs. Deploy tools require an explicit armed window.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from kernel.config import load_config

# Built-in fallback if YAML is missing/corrupt — preserves fail-closed behavior.
_DEFAULT_OFFENSIVE = {
    "nmap", "nikto", "osint", "recon", "geoip", "geoint",
    "dnsenum", "reversedns", "email_osint", "sigint",
    "headers", "cert", "whois", "dig", "ping", "traceroute",
}
_DEFAULT_DEPLOY = {
    "github_create_repo", "github_push", "supabase_migrate",
    "vercel_deploy", "netlify_deploy", "railway_deploy",
    "cloudflare_deploy", "stripe_trigger",
}
_DEFAULT_MESSAGES = {
    "deploy_denied": (
        "BLOCKED: '{tool}' requires an armed deploy window. "
        "Use /scope arm-deploy <minutes> to authorize, then retry."
    ),
    "scope_denied": (
        "BLOCKED: '{target}' is not in the authorized scope. "
        "Use /scope add {target} to explicitly authorize it first."
    ),
}

_policy_cache: dict[str, Any] | None = None
_policy_mtime: float | None = None


def _base() -> str:
    return str(load_config().base)


def _scope_path() -> str:
    return str(load_config().scope_path)


def _policy_path() -> Path:
    env = os.environ.get("KERROS_SCOPE_POLICY")
    if env:
        return Path(env).expanduser().resolve()
    cfg = load_config()
    return (cfg.base / "config" / "scope_policy.yaml").resolve()


def _audit(decision_type: str, input_summary: str, outcome: str, reason: str = "") -> None:
    try:
        from kernel.decision_log import record_decision
        record_decision("scope_gate", decision_type, input_summary, outcome, reason)
    except Exception:
        pass


def load_policy(*, force: bool = False) -> dict[str, Any]:
    """Load declarative scope policy from YAML (cached; reloads on mtime change)."""
    global _policy_cache, _policy_mtime
    path = _policy_path()
    try:
        mtime = path.stat().st_mtime if path.exists() else None
    except OSError:
        mtime = None

    if (
        not force
        and _policy_cache is not None
        and mtime is not None
        and mtime == _policy_mtime
    ):
        return _policy_cache

    policy: dict[str, Any] = {
        "version": 1,
        "defaults": {
            "fail_closed": True,
            "require_explicit_authorization": True,
            "deploy_arm_minutes": 5,
            "unknown_tools_are_passive": True,
        },
        "offensive_tools": set(_DEFAULT_OFFENSIVE),
        "deploy_tools": set(_DEFAULT_DEPLOY),
        "messages": dict(_DEFAULT_MESSAGES),
    }

    if path.exists():
        try:
            import yaml
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                defaults = raw.get("defaults") or {}
                if isinstance(defaults, dict):
                    policy["defaults"].update(defaults)
                if "offensive_tools" in raw and isinstance(raw["offensive_tools"], list):
                    policy["offensive_tools"] = {
                        str(x).strip() for x in raw["offensive_tools"] if str(x).strip()
                    }
                if "deploy_tools" in raw and isinstance(raw["deploy_tools"], list):
                    policy["deploy_tools"] = {
                        str(x).strip() for x in raw["deploy_tools"] if str(x).strip()
                    }
                messages = raw.get("messages") or {}
                if isinstance(messages, dict):
                    for key, val in messages.items():
                        if isinstance(val, str) and val.strip():
                            policy["messages"][key] = " ".join(val.split())
                policy["version"] = raw.get("version", 1)
                policy["source"] = str(path)
        except Exception:
            # Fail closed to built-in defaults if YAML is unreadable.
            policy["source"] = f"defaults(fallback:{path})"
    else:
        policy["source"] = "defaults(builtin)"

    _policy_cache = policy
    _policy_mtime = mtime
    return policy


def reload_policy() -> dict[str, Any]:
    return load_policy(force=True)


def _offensive_tools() -> set[str]:
    return set(load_policy()["offensive_tools"])


def _deploy_tools() -> set[str]:
    return set(load_policy()["deploy_tools"])


# Backward-compatible module-level names (snapshot at import; prefer helpers).
OFFENSIVE_TOOLS = set(_DEFAULT_OFFENSIVE)
DEPLOY_TOOLS = set(_DEFAULT_DEPLOY)


def _sync_public_sets() -> None:
    global OFFENSIVE_TOOLS, DEPLOY_TOOLS
    policy = load_policy()
    OFFENSIVE_TOOLS = set(policy["offensive_tools"])
    DEPLOY_TOOLS = set(policy["deploy_tools"])


def _arm_status():
    scope = _load_scope()
    until = scope.get("deploy_armed_until", 0)
    return until, time.time() < until


def arm_deploy(minutes=None):
    """Opens a time-limited window during which deploy tools will run.
    Call this only from an explicit human-issued command, never
    automatically from agent reasoning."""
    if minutes is None:
        minutes = int(load_policy()["defaults"].get("deploy_arm_minutes", 5))
    minutes = max(1, int(minutes))
    scope = _load_scope()
    scope["deploy_armed_until"] = time.time() + (minutes * 60)
    _save_scope(scope)
    _audit("deploy_arm", f"minutes={minutes}", "armed", f"until={scope['deploy_armed_until']}")
    return minutes


def disarm_deploy():
    scope = _load_scope()
    scope["deploy_armed_until"] = 0
    _save_scope(scope)
    _audit("deploy_arm", "manual", "disarmed", "")


def _load_scope():
    path = _scope_path()
    if not os.path.exists(path):
        return {
            "authorized_targets": [],
            "authorized_cidrs": [],
            "require_explicit_authorization": True,
        }
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {
            "authorized_targets": [],
            "authorized_cidrs": [],
            "require_explicit_authorization": True,
        }


def _save_scope(scope):
    path = _scope_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(scope, f, indent=2)


def _extract_target(args):
    """args may be a string target or a tuple - normalize to a bare string."""
    if isinstance(args, (list, tuple)):
        return str(args[0]) if args else ""
    return str(args or "")


def is_authorized(target):
    """Returns True if target is explicitly allowlisted (exact match, domain, or CIDR)."""
    if not target:
        return False

    scope = _load_scope()
    target = target.strip().lower()
    # Strip protocol/path if a URL was passed
    target = re.sub(r'^https?://', '', target).split('/')[0]

    authorized = [t.lower() for t in scope.get("authorized_targets", [])]
    if target in authorized:
        return True

    # CIDR check for IPs
    try:
        ip = ipaddress.ip_address(target)
        for cidr in scope.get("authorized_cidrs", []):
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
    except ValueError:
        pass  # not an IP, skip CIDR check

    return False


def requires_gate(tool):
    _sync_public_sets()
    return tool in _offensive_tools()


def tool_class(tool: str) -> str:
    """Return policy class for a tool: deploy | offensive | passive."""
    _sync_public_sets()
    if tool in _deploy_tools():
        return "deploy"
    if tool in _offensive_tools():
        return "offensive"
    return "passive"


def check(tool, args):
    """
    Main gate entry point. Returns (allowed: bool, reason: str).
    Call this BEFORE run_tool() for any offensive OR deploy tool.
    """
    _sync_public_sets()
    policy = load_policy()
    messages = policy["messages"]

    if tool in _deploy_tools():
        until, armed = _arm_status()
        if armed:
            remaining = int(until - time.time())
            _audit("deploy_check", tool, "allowed", f"{remaining}s remaining")
            return True, f"deploy armed, {remaining}s remaining"
        _audit("deploy_check", tool, "denied", "deploy window not armed")
        msg = messages.get("deploy_denied", _DEFAULT_MESSAGES["deploy_denied"])
        return False, msg.format(tool=tool)

    if not requires_gate(tool):
        return True, "passive tool, no gate required"

    target = _extract_target(args)
    if is_authorized(target):
        _audit("scope_check", f"{tool}:{target}", "allowed", "target authorized")
        return True, "authorized"

    _audit("scope_check", f"{tool}:{target}", "denied", "target not in scope")
    msg = messages.get("scope_denied", _DEFAULT_MESSAGES["scope_denied"])
    return False, msg.format(tool=tool, target=target)


def add_target(target):
    scope = _load_scope()
    target = target.strip().lower()
    if target not in scope.get("authorized_targets", []):
        scope.setdefault("authorized_targets", []).append(target)
        _save_scope(scope)
        _audit("scope_add", target, "added", "")
        return True
    return False


def remove_target(target):
    scope = _load_scope()
    target = target.strip().lower()
    if target in scope.get("authorized_targets", []):
        scope["authorized_targets"].remove(target)
        _save_scope(scope)
        _audit("scope_remove", target, "removed", "")
        return True
    return False


def list_scope():
    scope = _load_scope()
    return scope.get("authorized_targets", []), scope.get("authorized_cidrs", [])


def policy_summary() -> dict[str, Any]:
    policy = load_policy()
    return {
        "source": policy.get("source"),
        "version": policy.get("version"),
        "offensive_tools": sorted(policy["offensive_tools"]),
        "deploy_tools": sorted(policy["deploy_tools"]),
        "defaults": dict(policy["defaults"]),
    }


# Sync public sets from YAML on first import.
_sync_public_sets()
