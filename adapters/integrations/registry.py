"""
adapters/integrations/registry.py
=================================
Soft adaptive integrations catalog over ``api_config.yaml`` (ADR-055).

Reports which providers/tools have env credentials set (never prints secrets).
Resolves Sol/Terra/Luna/coding/research tiers to the first ready provider.
Does not call remote APIs or install SDKs.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "api_config.yaml"

# Categories scanned for status / capabilities.
CATALOG_SECTIONS = (
    "llm_cloud",
    "llm_local",
    "vector_db",
    "database",
    "storage",
    "search_and_research",
    "academic_writing",
    "image_generation",
    "tts",
    "coding_agents",
    "agent_frameworks",
    "browser_automation",
    "apache_services",
    "utility_services",
    "deploy",
    "app_specific",
)

_ENV_SUFFIX_KEYS = (
    "env",
    "api_env",
    "pat_env",
    "token_env",
    "legacy_token_env",
    "api_key_env",
    "secret_key_env",
    "publishable_key_env",
    "access_token_env",
    "service_role_key_env",
    "anon_key_env",
    "url_env",
    "db_url_env",
    "project_id_env",
    "org_id_env",
    "owner_env",
    "repo_env",
    "account_id_env",
    "zone_id_env",
    "team_id_env",
    "org_name_env",
    "ssh_key_env",
    "widget_key_env",
    "bootstrap_servers_env",
    "master_url_env",
    "api_url_env",
    "endpoint_env",
    "model_env",
    "author_name_env",
    "author_email_env",
    "legacy_key_env",
)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def load_registry(path: Optional[Path] = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if yaml is None or not cfg_path.is_file():
        return {}
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _env_get(names: Iterable[str]) -> tuple[str, str]:
    """Return (name, value) for first non-empty env among names."""
    for name in names:
        if not name:
            continue
        val = os.environ.get(str(name), "")
        if str(val).strip():
            return str(name), str(val)
    return "", ""


def _collect_env_names(entry: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in _ENV_SUFFIX_KEYS:
        raw = entry.get(key)
        if isinstance(raw, str) and raw.strip():
            names.append(raw.strip())
    aliases = entry.get("env_aliases") or []
    if isinstance(aliases, list):
        for a in aliases:
            if isinstance(a, str) and a.strip():
                names.append(a.strip())
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _entry_ready(entry: dict[str, Any]) -> dict[str, Any]:
    """Classify one leaf entry."""
    env_names = _collect_env_names(entry)
    default = entry.get("default")
    cli = entry.get("cli")
    hit_env, _ = _env_get(env_names) if env_names else ("", "")
    cli_ok = bool(cli and shutil.which(str(cli)))
    # Endpoint-only locals with defaults count as soft-ready when default present
    # but still "needs_setup" for cloud keys; mark configured if env or cli.
    configured = bool(hit_env) or cli_ok
    soft_default = bool(default) and not env_names
    status = "ready" if configured else ("soft_default" if soft_default else "needs_setup")
    return {
        "status": status,
        "configured": configured,
        "env_checked": env_names,
        "env_hit": hit_env or None,
        "cli": cli,
        "cli_present": cli_ok if cli else None,
        "notes": entry.get("notes") or entry.get("docs") or "",
        "base_url": entry.get("base_url") or entry.get("default"),
        "model": entry.get("model"),
    }


def _is_leaf(entry: dict[str, Any]) -> bool:
    if any(k in entry for k in _ENV_SUFFIX_KEYS):
        return True
    if any(k in entry for k in ("notes", "cli", "docs", "pip", "model_env")):
        return True
    return False


def _walk_section(section: Any, prefix: str = "") -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    if not isinstance(section, dict):
        return items
    for name, val in section.items():
        path = f"{prefix}.{name}" if prefix else str(name)
        if not isinstance(val, dict):
            continue
        nested_dicts = {k: v for k, v in val.items() if isinstance(v, dict)}
        if _is_leaf(val):
            items.append((path, val))
        if nested_dicts:
            items.extend(_walk_section(nested_dicts, path))
    return items


def catalog_status(
    cfg: Optional[dict[str, Any]] = None,
    *,
    sections: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    data = cfg if cfg is not None else load_registry()
    want = tuple(sections) if sections else CATALOG_SECTIONS
    out: dict[str, Any] = {"ok": True, "sections": {}, "ready": [], "needs_setup": []}
    for section in want:
        block = data.get(section) or {}
        rows: dict[str, Any] = {}
        for path, entry in _walk_section(block):
            # Skip pure metadata keys like backend_env-only without treating twice
            info = _entry_ready(entry)
            rows[path] = info
            label = f"{section}:{path}"
            if info["configured"]:
                out["ready"].append(label)
            elif info["status"] == "needs_setup":
                out["needs_setup"].append(label)
        out["sections"][section] = rows
    out["ready_count"] = len(out["ready"])
    out["needs_setup_count"] = len(out["needs_setup"])
    return out


def list_tiers(cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = cfg if cfg is not None else load_registry()
    tiers = data.get("routing_tiers") or {}
    return tiers if isinstance(tiers, dict) else {}


def resolve_tier(
    tier: str,
    cfg: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Return first configured LLM provider in a routing tier."""
    data = cfg if cfg is not None else load_registry()
    tiers = list_tiers(data)
    name = (tier or "").strip().lower()
    spec = tiers.get(name) if isinstance(tiers, dict) else None
    if not isinstance(spec, dict):
        return {"ok": False, "tier": name, "error": "unknown_tier", "provider": None}
    providers = list(spec.get("providers") or [])
    cloud = data.get("llm_cloud") or {}
    local = data.get("llm_local") or {}
    tried: list[str] = []
    for prov in providers:
        entry = cloud.get(prov) or local.get(prov)
        if not isinstance(entry, dict):
            tried.append(prov)
            continue
        info = _entry_ready(entry)
        tried.append(prov)
        if info["configured"] or (
            info["status"] == "soft_default" and prov in local
        ):
            return {
                "ok": True,
                "tier": name,
                "provider": prov,
                "description": spec.get("description"),
                "model": entry.get("model"),
                "base_url": entry.get("base_url") or entry.get("default"),
                "tried": tried,
                "status": info["status"],
            }
    return {
        "ok": False,
        "tier": name,
        "error": "no_provider_configured",
        "provider": None,
        "description": spec.get("description"),
        "tried": tried,
    }


def prefer_task_tier(task: str) -> str:
    t = (task or "").strip().lower()
    if t in ("code", "coding", "exec", "execution", "dev"):
        return "coding"
    if t in ("research", "paper", "academic", "rag"):
        return "research"
    if t in ("fast", "sol", "cheap"):
        return "sol"
    if t in ("heavy", "luna", "quality"):
        return "luna"
    if t in ("terra", "balanced"):
        return "terra"
    env = os.environ.get("KERROS_ROUTING_TIER", "").strip().lower()
    return env or "terra"


def adaptive_coding_enabled(cfg: Optional[dict[str, Any]] = None) -> bool:
    _ = cfg
    return _truthy(os.environ.get("KERROS_ADAPTIVE_CODING", "1"))


def resolve_for_task(task: str = "coding") -> dict[str, Any]:
    tier = prefer_task_tier(task)
    return resolve_tier(tier)


def format_status_lines(
    status: Optional[dict[str, Any]] = None,
    *,
    section: Optional[str] = None,
    ready_only: bool = False,
) -> list[str]:
    st = status or catalog_status(sections=[section] if section else None)
    lines: list[str] = [
        f"integrations ready={st.get('ready_count', 0)} "
        f"needs_setup={st.get('needs_setup_count', 0)}"
    ]
    sections = st.get("sections") or {}
    for sec, rows in sections.items():
        if section and sec != section:
            continue
        lines.append(f"[{sec}]")
        for path, info in rows.items():
            if ready_only and not info.get("configured"):
                continue
            flag = "OK" if info.get("configured") else info.get("status", "?")
            hit = info.get("env_hit") or (info.get("cli") if info.get("cli_present") else "-")
            lines.append(f"  {flag:12s} {path:<28s} ({hit})")
    return lines
