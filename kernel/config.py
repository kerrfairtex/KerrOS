"""
kernel/config.py
================
Kernel configuration system — typed, validated access to runtime settings.

Loads .env + config.json (via core/config.py) and adds kernel-specific
paths (base, workspace, scope). This is the only supported way for kernel
code and boot to read configuration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _detect_base() -> Path:
    env_base = os.environ.get("KERROS_BASE") or os.environ.get("OFFLINE_AI_BASE")
    if env_base:
        return Path(env_base).expanduser().resolve()

    termux = Path("/data/data/com.termux/files/home/offline_ai")
    if termux.exists():
        return termux.resolve()

    # Repo / workspace root fallback (cloud dev, local clone).
    repo = Path(__file__).resolve().parent.parent
    if (repo / "config.json").exists():
        return repo.resolve()

    return Path(os.path.expanduser("~/offline_ai")).resolve()


@dataclass
class KernelConfig:
    """Validated kernel configuration snapshot."""

    base: Path
    workspace: Path
    scope_path: Path
    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self.values:
            raise KeyError(f"required config key missing: {key}")
        return self.values[key]

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": str(self.base),
            "workspace": str(self.workspace),
            "scope_path": str(self.scope_path),
            **self.values,
        }


def _load_raw(base: Path) -> dict[str, Any]:
    """Load config using core/config when available, else direct JSON."""
    try:
        import core.config as legacy

        legacy.BASE = base
        legacy._cfg = None  # reset singleton for new base
        return legacy.load()
    except Exception:
        cfg_path = base / "config.json"
        if not cfg_path.exists():
            return {}
        with open(cfg_path) as f:
            return json.load(f)


def load_config(*, base: Path | None = None) -> KernelConfig:
    """Load and validate kernel configuration."""
    root = (base or _detect_base()).expanduser().resolve()
    raw = _load_raw(root)

    workspace = Path(
        os.environ.get(
            "KERROS_WORKSPACE",
            os.environ.get("KERROS_PROJECT_ROOT", str(root)),
        )
    ).expanduser().resolve()

    scope = root / "config" / "scope.json"
    # Do not fall back to the repo scope.json when KERROS_BASE/OFFLINE_AI_BASE
    # (or an explicit base=) isolates the runtime — that would leak arm/allow
    # state across test sandboxes and alternate installs.
    if not scope.exists() and base is None and not (
        os.environ.get("KERROS_BASE") or os.environ.get("OFFLINE_AI_BASE")
    ):
        scope = Path(__file__).resolve().parent.parent / "config" / "scope.json"

    defaults = {
        "llm_route_policy": "legacy_fallback",
        "llm_provider_default": "cloud",
        "use_omniroute": False,
        "omniroute_url": "http://127.0.0.1:20128/v1",
        "qdrant_enabled": False,
        "qdrant_url": "http://127.0.0.1:6333",
        # KerrOS-only collection — do not reuse OmniRoute vector namespaces (P5).
        "qdrant_collection": "kerros_memory",
        # P6: composite provider circuit breaker / cooldown / lockout.
        "llm_resilience": {
            "enabled": True,
            "failure_threshold": 3,
            "cooldown_s": 30,
            "lockout_opens": 3,
            "lockout_s": 300,
        },
        # P3/C-16 event mesh foundation — off by default; full multi-node broker deferred.
        "event_mesh": {
            "enabled": False,
            "node_id": "local",
            "transport": "null",
            "file_dir": "data/event_mesh",
            "http_peers": [],
        },
    }
    merged = {**defaults, **raw}

    return KernelConfig(
        base=root,
        workspace=workspace,
        scope_path=scope.resolve(),
        values=merged,
    )


def reload_config(*, base: Path | None = None) -> KernelConfig:
    """Force reload configuration (clears core/config singleton)."""
    try:
        import core.config as legacy

        legacy._cfg = None
    except Exception:
        pass
    return load_config(base=base)
