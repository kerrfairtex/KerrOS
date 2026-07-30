"""
adapters/llm/offline_profile.py
================================
Load KerrOS offline profiles (Phase A / ADR-050).

Default-off. ``KERROS_OFFLINE_PROFILE=offline_qwen05`` selects
``config/profiles/offline_qwen05.yaml``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
PROFILES_DIR = ROOT / "config" / "profiles"
DEFAULT_PROFILE = "offline_qwen05"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def profile_name_from_env(cfg: Mapping[str, Any] | None = None) -> str:
    data = dict(cfg or {})
    env = os.environ.get("KERROS_OFFLINE_PROFILE", "").strip()
    if env:
        return env
    return str(data.get("offline_profile") or "").strip()


def is_offline_profile_active(cfg: Mapping[str, Any] | None = None) -> bool:
    name = profile_name_from_env(cfg)
    if name:
        return True
    provider = (
        os.environ.get("KERROS_LLM_PROVIDER")
        or str((cfg or {}).get("llm_provider_default") or "")
    ).strip().lower()
    if provider in ("llama_cpp", "llamacpp", "offline"):
        return True
    return False


def resolve_profile_path(name: str, *, base: Optional[Path] = None) -> Path:
    root = base or ROOT
    clean = name.strip().replace("..", "").strip("/\\")
    if not clean:
        clean = DEFAULT_PROFILE
    if not clean.endswith(".yaml") and not clean.endswith(".yml"):
        clean = f"{clean}.yaml"
    return root / "config" / "profiles" / clean


def load_offline_profile(
    name: Optional[str] = None,
    *,
    base: Optional[Path] = None,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load a profile YAML. Returns {} if missing or inactive without a name."""
    resolved_name = (name or profile_name_from_env(cfg) or "").strip()
    if not resolved_name:
        if is_offline_profile_active(cfg):
            resolved_name = DEFAULT_PROFILE
        else:
            return {}
    path = resolve_profile_path(resolved_name, base=base)
    if not path.is_file():
        return {"name": resolved_name, "error": f"profile not found: {path}", "ok": False}
    if yaml is None:
        return {"name": resolved_name, "error": "PyYAML required", "ok": False}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {"name": resolved_name, "error": "invalid profile YAML", "ok": False}
    data = dict(data)
    data["ok"] = True
    data["_path"] = str(path)
    return data


def profile_gguf_path(
    profile: Mapping[str, Any] | None = None,
    *,
    base: Optional[Path] = None,
) -> Path:
    root = base or ROOT
    data = dict(profile or {})
    model = data.get("model") if isinstance(data.get("model"), dict) else {}
    rel = (
        os.environ.get("MODEL_PATH")
        or os.environ.get("KERROS_LLAMA_CPP_MODEL")
        or (model or {}).get("gguf")
        or "models/qwen0.5b-q4.gguf"
    )
    path = Path(str(rel)).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def profile_prompt_format(profile: Mapping[str, Any] | None = None) -> str:
    data = dict(profile or {})
    fmt = str(data.get("prompt_format") or "chatml").strip().lower()
    return fmt or "chatml"
