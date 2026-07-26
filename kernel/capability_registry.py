"""
kernel/capability_registry.py
=============================
Kernel-managed capability registry with manifest + setup lifecycle state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Capability IDs are lowercase namespaced tokens (e.g., tool:exec, workflow:build.docs)
# constrained to 2..80 chars for stable storage and CLI display.
_CAPABILITY_NAME_RE = re.compile(r"^[a-z0-9_.:-]{2,80}$")


@dataclass
class Capability:
    name: str
    kind: str
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    setup_required: bool = False
    setup_state: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}

    def upsert(self, cap: Capability) -> None:
        if not _CAPABILITY_NAME_RE.match(cap.name):
            raise ValueError(f"invalid capability name: {cap.name}")
        self._caps[cap.name] = cap

    def register(
        self,
        *,
        name: str,
        kind: str,
        permissions: list[str] | None = None,
        dependencies: list[str] | None = None,
        setup_required: bool = False,
        setup_state: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.upsert(
            Capability(
                name=name,
                kind=kind,
                permissions=list(permissions or []),
                dependencies=list(dependencies or []),
                setup_required=setup_required,
                setup_state=setup_state,
                metadata=dict(metadata or {}),
            )
        )

    def get(self, name: str) -> Capability | None:
        return self._caps.get(name)

    def list(self, kind: str | None = None) -> list[Capability]:
        vals = list(self._caps.values())
        if kind:
            vals = [c for c in vals if c.kind == kind]
        return sorted(vals, key=lambda c: c.name)

    def mark_setup(self, name: str, state: str) -> None:
        cap = self.get(name)
        if not cap:
            raise KeyError(f"unknown capability: {name}")
        cap.setup_state = state

    def load_manifest_dir(self, path: Path) -> int:
        if not path.exists():
            return 0
        loaded = 0
        for p in sorted(path.glob("*.yaml")):
            loaded += self.load_manifest_file(p)
        return loaded

    def load_manifest_file(self, path: Path) -> int:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = raw.get("capabilities", []) if isinstance(raw, dict) else []
        loaded = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            self.register(
                name=str(entry.get("name", "")).strip(),
                kind=str(entry.get("kind", "tool")).strip(),
                permissions=[str(x) for x in entry.get("permissions", [])],
                dependencies=[str(x) for x in entry.get("dependencies", [])],
                setup_required=bool(entry.get("setup_required", False)),
                setup_state=str(entry.get("setup_state", "unknown")),
                metadata=dict(entry.get("metadata", {})),
            )
            loaded += 1
        return loaded

    def bootstrap_from_tool_definitions(self, tool_definitions: list[dict[str, Any]]) -> int:
        loaded = 0
        for tool in tool_definitions:
            fn = tool.get("function", {})
            name = str(fn.get("name", "")).strip()
            if not name:
                continue
            permissions = ["standard"]
            if name in {"exec", "apply_patch", "remove"}:
                permissions = ["elevated"]
            self.register(
                name=f"tool:{name}",
                kind="tool",
                permissions=permissions,
                dependencies=[],
                setup_required=name == "exec",
                setup_state="ready" if name != "exec" else "needs_setup",
                metadata={"description": fn.get("description", "")},
            )
            loaded += 1
        return loaded
