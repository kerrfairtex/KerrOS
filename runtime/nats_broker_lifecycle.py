"""
runtime/nats_broker_lifecycle.py
================================
NATS broker *process lifecycle* foundation (ADR-033).

Default-off. Manages start/stop/status for a ``nats-server`` process via
an injectable backend. CI uses ``InMemoryBrokerProcess`` (no spawn).
Real subprocess spawn requires ``allow_spawn`` and a binary on PATH.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from runtime.nats_supercluster import _truthy


class BrokerLifecycleError(RuntimeError):
    """Broker process lifecycle failed."""


@runtime_checkable
class BrokerProcessBackend(Protocol):
    def start(self) -> dict[str, Any]: ...

    def stop(self) -> dict[str, Any]: ...

    def status(self) -> dict[str, Any]: ...


@dataclass
class InMemoryBrokerProcess:
    """CI-safe fake broker process."""

    name: str = "nats-server"
    _running: bool = False
    _pid: int = 0
    _starts: int = 0
    _stops: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._running:
                return {"ok": True, "already": True, "pid": self._pid}
            self._starts += 1
            self._pid = 10_000 + self._starts
            self._running = True
            return {"ok": True, "pid": self._pid, "backend": "memory"}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._running:
                return {"ok": True, "already": True}
            self._stops += 1
            self._running = False
            pid = self._pid
            self._pid = 0
            return {"ok": True, "pid": pid, "backend": "memory"}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "pid": self._pid,
                "starts": self._starts,
                "stops": self._stops,
                "backend": "memory",
                "name": self.name,
            }


@dataclass
class SubprocessBrokerProcess:
    """Soft real ``nats-server`` subprocess manager."""

    bin_name: str = "nats-server"
    config_path: str = ""
    extra_args: list[str] = field(default_factory=list)
    allow_spawn: bool = False
    _proc: subprocess.Popen | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> dict[str, Any]:
        if not self.allow_spawn:
            return {"ok": False, "skipped": True, "error": "spawn disabled"}
        path = shutil.which(self.bin_name)
        if not path:
            return {"ok": False, "error": f"{self.bin_name} not on PATH"}
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return {"ok": True, "already": True, "pid": self._proc.pid}
            cmd = [path]
            if self.config_path:
                cmd.extend(["-c", self.config_path])
            cmd.extend(self.extra_args)
            try:
                self._proc = subprocess.Popen(  # noqa: S603
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(0.05)
                if self._proc.poll() is not None:
                    code = self._proc.returncode
                    self._proc = None
                    return {"ok": False, "error": f"exited early code={code}"}
                return {"ok": True, "pid": self._proc.pid, "backend": "subprocess"}
            except Exception as exc:
                self._proc = None
                return {"ok": False, "error": str(exc)}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._proc is None:
                return {"ok": True, "already": True}
            proc = self._proc
            self._proc = None
        try:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
            return {"ok": True, "pid": proc.pid, "backend": "subprocess"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            return {
                "running": running,
                "pid": self._proc.pid if running and self._proc else 0,
                "backend": "subprocess",
                "allow_spawn": self.allow_spawn,
                "bin": self.bin_name,
            }


@dataclass
class BrokerLifecycleConfig:
    enabled: bool = False
    backend: str = "memory"  # memory | subprocess
    bin_name: str = "nats-server"
    config_path: str = ""
    allow_spawn: bool = False
    extra_args: list[str] = field(default_factory=list)
    autostart: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "BrokerLifecycleConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_NATS_BROKER")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_NATS_BROKER_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "memory")

        bin_name = os.environ.get("KERROS_ACTOR_MESH_NATS_SERVER_BIN")
        if bin_name is None:
            bin_name = str(data.get("bin_name") or "nats-server")

        config_path = os.environ.get("KERROS_ACTOR_MESH_NATS_BROKER_CONFIG")
        if config_path is None:
            config_path = str(data.get("config_path") or "")
        cfg_path = Path(config_path) if config_path else Path("")
        if config_path and not cfg_path.is_absolute() and base is not None:
            cfg_path = Path(base) / cfg_path

        allow_spawn = data.get("allow_spawn", False)
        env_s = os.environ.get("KERROS_ACTOR_MESH_NATS_BROKER_SPAWN")
        if env_s is not None:
            allow_spawn = _truthy(env_s)
        else:
            allow_spawn = _truthy(allow_spawn)

        autostart = data.get("autostart", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_NATS_BROKER_AUTOSTART")
        if env_a is not None:
            autostart = _truthy(env_a)
        else:
            autostart = _truthy(autostart)

        args_raw = data.get("extra_args") or []
        if isinstance(args_raw, str):
            args = [a for a in args_raw.split() if a]
        else:
            args = [str(a) for a in args_raw if str(a).strip()]

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "memory").strip().lower() or "memory",
            bin_name=str(bin_name or "nats-server").strip() or "nats-server",
            config_path=str(cfg_path) if config_path else "",
            allow_spawn=bool(allow_spawn),
            extra_args=args,
            autostart=bool(autostart),
        )


@dataclass
class NatsBrokerLifecycle:
    """Facade for broker process start/stop/status."""

    cfg: BrokerLifecycleConfig
    backend: BrokerProcessBackend = field(default_factory=InMemoryBrokerProcess)

    def start(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise BrokerLifecycleError("broker lifecycle disabled")
        return self.backend.start()

    def stop(self) -> dict[str, Any]:
        return self.backend.stop()

    def status(self) -> dict[str, Any]:
        return self.backend.status()

    def restart(self) -> dict[str, Any]:
        self.stop()
        return self.start()

    def stats(self) -> dict[str, Any]:
        st = self.status()
        return {
            "enabled": self.cfg.enabled,
            "backend": self.cfg.backend,
            "allow_spawn": self.cfg.allow_spawn,
            "autostart": self.cfg.autostart,
            "config_path": self.cfg.config_path,
            **st,
        }


def build_nats_broker_lifecycle(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    backend: BrokerProcessBackend | None = None,
    base: Optional[Path] = None,
) -> NatsBrokerLifecycle | None:
    lc = BrokerLifecycleConfig.from_mapping(cfg, base=base)
    if not lc.enabled:
        return None
    if backend is not None:
        be = backend
    elif lc.backend in ("subprocess", "process", "real"):
        be = SubprocessBrokerProcess(
            bin_name=lc.bin_name,
            config_path=lc.config_path,
            extra_args=list(lc.extra_args),
            allow_spawn=lc.allow_spawn,
        )
    else:
        be = InMemoryBrokerProcess(name=lc.bin_name)
    mgr = NatsBrokerLifecycle(cfg=lc, backend=be)
    if lc.autostart:
        try:
            mgr.start()
        except Exception:
            pass
    return mgr
