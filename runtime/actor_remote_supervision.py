"""
runtime/actor_remote_supervision.py
===================================
Optional remote / managed-process restart hooks for ActorSupervisor (ADR-023).

Default-off. Maps actor name → ServiceManager service name and calls
``restart`` on DEAD transitions. Not an OTP supervision tree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol

from runtime.actor_supervision import ActorLiveness, RestartHook


class ServiceRestarter(Protocol):
    def restart(self, name: str) -> bool:
        ...


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class RemoteSupervisionConfig:
    """Opt-in process restart wiring (ADR-023)."""

    remote_restart: bool = False
    process_map: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls, raw: Optional[Mapping[str, Any]] = None
    ) -> "RemoteSupervisionConfig":
        data = dict(raw or {})
        enabled = data.get("remote_restart", False)
        env = os.environ.get("KERROS_ACTOR_MESH_REMOTE_RESTART")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        proc_map: dict[str, str] = {}
        raw_map = data.get("process_map") or {}
        if isinstance(raw_map, dict):
            for k, v in raw_map.items():
                key = str(k).strip()
                val = str(v).strip()
                if key and val:
                    proc_map[key] = val

        env_map = os.environ.get("KERROS_ACTOR_MESH_PROCESS_MAP")
        if env_map:
            # actor=service,actor2=service2
            for part in env_map.split(","):
                part = part.strip()
                if not part or "=" not in part:
                    continue
                a, _, s = part.partition("=")
                a, s = a.strip(), s.strip()
                if a and s:
                    proc_map[a] = s

        return cls(remote_restart=bool(enabled), process_map=proc_map)


@dataclass
class RemoteRestartHook:
    """RestartHook that records attempts and optionally calls ServiceManager."""

    process_map: dict[str, str]
    manager: ServiceRestarter | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, name: str, row: ActorLiveness) -> None:
        service = self.process_map.get(str(name or "").strip())
        record: dict[str, Any] = {
            "actor": name,
            "service": service,
            "node_id": row.node_id,
            "status": row.status.value,
            "restarted": False,
            "error": "",
        }
        if not service:
            record["error"] = "no process_map entry"
            self.attempts.append(record)
            return
        if self.manager is None:
            record["error"] = "no service manager bound"
            self.attempts.append(record)
            return
        try:
            ok = bool(self.manager.restart(service))
            record["restarted"] = ok
            if not ok:
                record["error"] = "restart returned false"
        except Exception as exc:
            record["error"] = str(exc)
        self.attempts.append(record)


def build_remote_restart_hook(
    *,
    cfg: RemoteSupervisionConfig,
    manager: ServiceRestarter | None = None,
) -> RestartHook | None:
    if not cfg.remote_restart:
        return None
    return RemoteRestartHook(process_map=dict(cfg.process_map), manager=manager)
