"""
runtime/nats_remote_fleet.py
============================
Remote fleet *orchestration* foundation (ADR-037).

Default-off. Drives start/stop/status on remote hosts via an injectable
agent transport (in-memory Fake for CI, soft HTTP webhook, soft SSH).
Does **not** require live SSH or remote nats-server in tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.nats_supercluster import _truthy


class RemoteFleetError(RuntimeError):
    """Remote fleet orchestration failed."""


@runtime_checkable
class RemoteAgentTransport(Protocol):
    def exec_action(
        self, host: str, action: str, *, member: str = "", extra: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeRemoteAgentTransport:
    """CI-safe in-memory remote agent."""

    _hosts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _calls: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def exec_action(
        self, host: str, action: str, *, member: str = "", extra: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        h = str(host or "").strip() or "local"
        m = str(member or "broker").strip() or "broker"
        with self._lock:
            host_state = self._hosts.setdefault(h, {})
            member_state = host_state.setdefault(m, {"running": False, "pid": 0})
            if action == "start":
                member_state["running"] = True
                member_state["pid"] = member_state.get("pid") or (10_000 + len(self._calls) + 1)
            elif action == "stop":
                member_state["running"] = False
                member_state["pid"] = 0
            elif action == "status":
                pass
            elif action == "restart":
                member_state["running"] = True
                member_state["pid"] = 10_000 + len(self._calls) + 1
            else:
                return {"ok": False, "error": f"unknown action: {action}", "host": h}
            out = {
                "ok": True,
                "host": h,
                "member": m,
                "action": action,
                "running": bool(member_state["running"]),
                "pid": int(member_state["pid"]),
                "backend": "fake",
            }
            self._calls.append(dict(out))
            return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "backend": "fake",
                "hosts": len(self._hosts),
                "calls": len(self._calls),
            }


@dataclass
class HttpRemoteAgentTransport:
    """Soft POST to ``{base_url}/fleet/{host}/{member}/{action}``."""

    base_url: str
    token: str = ""
    allow_live: bool = False
    timeout_s: float = 5.0
    _shadow: FakeRemoteAgentTransport = field(default_factory=FakeRemoteAgentTransport)
    _last: dict[str, Any] = field(default_factory=dict)

    def exec_action(
        self, host: str, action: str, *, member: str = "", extra: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.exec_action(host, action, member=member, extra=extra)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        base = str(self.base_url or "").rstrip("/")
        if not base:
            raise RemoteFleetError("base_url required for live remote fleet")
        url = f"{base}/fleet/{host}/{member or 'broker'}/{action}"
        body = json.dumps(dict(extra or {})).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "kerros-remote-fleet/1"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            req = Request(url, data=body, method="POST", headers=headers)
            with urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                raw = resp.read(65536)
                data = json.loads(raw.decode("utf-8")) if raw else {}
            out = {
                "ok": True,
                "host": host,
                "member": member,
                "action": action,
                "status": getattr(resp, "status", 200),
                "body": data if isinstance(data, dict) else {},
                "backend": "http",
            }
            self._last = dict(out)
            return out
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            out = {"ok": False, "error": str(exc), "host": host, "action": action}
            self._last = dict(out)
            return out

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "http",
            "base_url": self.base_url,
            "allow_live": self.allow_live,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class SoftSshRemoteAgentTransport:
    """Soft ``ssh host -- kerros-fleet-agent <action>`` probe when allow_live."""

    ssh_bin: str = "ssh"
    allow_live: bool = False
    timeout_s: float = 10.0
    _shadow: FakeRemoteAgentTransport = field(default_factory=FakeRemoteAgentTransport)
    _last: dict[str, Any] = field(default_factory=dict)

    def exec_action(
        self, host: str, action: str, *, member: str = "", extra: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.exec_action(host, action, member=member, extra=extra)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        path = shutil.which(self.ssh_bin)
        if not path:
            return {"ok": False, "skipped": True, "error": f"{self.ssh_bin} not on PATH"}
        cmd = [
            path,
            str(host),
            "--",
            "kerros-fleet-agent",
            action,
            "--member",
            member or "broker",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
            out = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-1000:],
                "stderr": (proc.stderr or "")[-1000:],
                "host": host,
                "action": action,
                "backend": "ssh",
            }
            self._last = dict(out)
            return out
        except Exception as exc:
            out = {"ok": False, "error": str(exc), "host": host, "action": action}
            self._last = dict(out)
            return out

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "ssh",
            "allow_live": self.allow_live,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class RemoteHostSpec:
    name: str
    host: str
    members: list[str] = field(default_factory=lambda: ["broker"])
    region: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "host": self.host,
            "members": list(self.members),
            "region": self.region,
        }


@dataclass
class RemoteFleetConfig:
    enabled: bool = False
    transport: str = "fake"  # fake | http | ssh
    allow_live: bool = False
    http_base_url: str = ""
    http_token: str = ""
    ssh_bin: str = "ssh"
    hosts: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "RemoteFleetConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_REMOTE_FLEET")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        transport = os.environ.get("KERROS_ACTOR_MESH_REMOTE_FLEET_TRANSPORT")
        if transport is None:
            transport = str(data.get("transport") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_REMOTE_FLEET_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        http_url = os.environ.get("KERROS_ACTOR_MESH_REMOTE_FLEET_HTTP")
        if http_url is None:
            http_url = str(data.get("http_base_url") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_REMOTE_FLEET_TOKEN")
        if token is None:
            token = str(data.get("http_token") or "")

        ssh_bin = os.environ.get("KERROS_ACTOR_MESH_REMOTE_FLEET_SSH")
        if ssh_bin is None:
            ssh_bin = str(data.get("ssh_bin") or "ssh")

        return cls(
            enabled=bool(enabled),
            transport=str(transport or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            http_base_url=str(http_url or "").strip(),
            http_token=str(token or "").strip(),
            ssh_bin=str(ssh_bin or "ssh").strip() or "ssh",
            hosts=list(data.get("hosts") or []),
        )


@dataclass
class RemoteFleetOrchestrator:
    """Orchestrate fleet actions across remote hosts."""

    cfg: RemoteFleetConfig
    transport: RemoteAgentTransport = field(default_factory=FakeRemoteAgentTransport)
    _hosts: list[RemoteHostSpec] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        for raw in self.cfg.hosts:
            name = str(raw.get("name") or raw.get("host") or "").strip()
            host = str(raw.get("host") or name).strip()
            if not name or not host:
                continue
            members = raw.get("members") or ["broker"]
            if isinstance(members, str):
                members = [m.strip() for m in members.split(",") if m.strip()]
            self._hosts.append(
                RemoteHostSpec(
                    name=name,
                    host=host,
                    members=[str(m) for m in members if str(m).strip()],
                    region=str(raw.get("region") or ""),
                )
            )

    def plan(self, action: str = "status") -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for spec in self._hosts:
            for member in spec.members:
                steps.append(
                    {
                        "host_name": spec.name,
                        "host": spec.host,
                        "member": member,
                        "action": action,
                        "region": spec.region,
                        "status": "planned",
                    }
                )
        return steps

    def apply(self, action: str = "start") -> dict[str, Any]:
        if not self.cfg.enabled:
            raise RemoteFleetError("remote fleet orchestration disabled")
        results: list[dict[str, Any]] = []
        for step in self.plan(action):
            out = self.transport.exec_action(
                step["host"], action, member=step["member"]
            )
            results.append({**step, "result": out, "status": "applied" if out.get("ok") else "failed"})
        ok = all(r.get("status") == "applied" for r in results) if results else True
        return {"ok": ok, "action": action, "results": results, "at": time.time()}

    def status_all(self) -> dict[str, Any]:
        return self.apply("status")

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "transport": self.cfg.transport,
                "allow_live": self.cfg.allow_live,
                "hosts": len(self._hosts),
                "planned_start": len(self.plan("start")),
                "transport_stats": self.transport.stats(),
                "hosts_detail": [h.to_dict() for h in self._hosts],
            }


def build_remote_fleet_orchestrator(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    transport: RemoteAgentTransport | None = None,
) -> RemoteFleetOrchestrator | None:
    rf_cfg = RemoteFleetConfig.from_mapping(cfg)
    if not rf_cfg.enabled:
        return None
    if transport is not None:
        tr = transport
    elif rf_cfg.transport == "http":
        tr = HttpRemoteAgentTransport(
            base_url=rf_cfg.http_base_url,
            token=rf_cfg.http_token,
            allow_live=rf_cfg.allow_live,
        )
    elif rf_cfg.transport == "ssh":
        tr = SoftSshRemoteAgentTransport(
            ssh_bin=rf_cfg.ssh_bin, allow_live=rf_cfg.allow_live
        )
    else:
        tr = FakeRemoteAgentTransport()
    return RemoteFleetOrchestrator(cfg=rf_cfg, transport=tr)
