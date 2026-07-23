"""
runtime/services.py
===================
KerrOS service manager (Phase 2).

Registers, starts, stops, and supervises managed subprocess services.
IPC-capable services use JSON-line protocol via runtime/ipc.py.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from runtime.ipc import IpcError, JsonLineClient, spawn_worker
from runtime.service_bus import ServiceBus


class ServiceState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"


@dataclass
class ServiceSpec:
    name: str
    command: Sequence[str]
    autostart: bool = False
    ipc: bool = False
    description: str = ""


@dataclass
class ManagedService:
    spec: ServiceSpec
    state: ServiceState = ServiceState.STOPPED
    proc: subprocess.Popen | None = None
    client: JsonLineClient | None = None
    started_at: float | None = None
    restart_count: int = 0
    last_error: str = ""


class ServiceManager:
    def __init__(self, bus: ServiceBus | None = None) -> None:
        self.bus = bus or ServiceBus()
        self._services: dict[str, ManagedService] = {}

    def register(self, spec: ServiceSpec) -> None:
        if spec.name in self._services:
            raise ValueError(f"service already registered: {spec.name}")
        self._services[spec.name] = ManagedService(spec=spec)
        self.bus.publish("service.registered", {"name": spec.name})

    def start(self, name: str) -> bool:
        svc = self._require(name)
        if svc.state == ServiceState.RUNNING and svc.proc and svc.proc.poll() is None:
            return True

        self._stop_process(svc)
        svc.state = ServiceState.STARTING
        svc.last_error = ""

        try:
            proc = spawn_worker(list(svc.spec.command))
            svc.proc = proc
            svc.started_at = time.time()

            if svc.spec.ipc:
                client = JsonLineClient(proc)
                client.call("ping", timeout=5)
                svc.client = client

            svc.state = ServiceState.RUNNING
            self.bus.publish("service.started", {"name": name})
            return True
        except Exception as exc:
            svc.state = ServiceState.CRASHED
            svc.last_error = str(exc)
            self._stop_process(svc)
            self.bus.publish("service.failed", {"name": name, "error": str(exc)})
            return False

    def stop(self, name: str) -> bool:
        svc = self._require(name)
        self._stop_process(svc)
        svc.state = ServiceState.STOPPED
        svc.started_at = None
        self.bus.publish("service.stopped", {"name": name})
        return True

    def restart(self, name: str) -> bool:
        self.stop(name)
        svc = self._require(name)
        svc.restart_count += 1
        return self.start(name)

    def call(self, name: str, method: str, params: dict[str, Any] | None = None) -> Any:
        svc = self._require(name)
        if not svc.spec.ipc or not svc.client:
            raise ValueError(f"service '{name}' is not IPC-enabled")
        if svc.proc and svc.proc.poll() is not None:
            self._mark_crashed(svc, "process exited")
            raise IpcError(f"service '{name}' is not running")
        try:
            return svc.client.call(method, params)
        except IpcError as exc:
            self._mark_crashed(svc, str(exc))
            raise

    def start_autostart(self) -> list[str]:
        started = []
        for name, svc in self._services.items():
            if svc.spec.autostart:
                if self.start(name):
                    started.append(name)
        return started

    def monitor(self) -> list[str]:
        """Check running services; restart crashed autostart services."""
        restarted: list[str] = []
        for name, svc in self._services.items():
            if svc.state != ServiceState.RUNNING or not svc.proc:
                continue
            if svc.proc.poll() is None:
                continue
            code = svc.proc.returncode
            self._mark_crashed(svc, f"exit code {code}")
            if svc.spec.autostart:
                svc.restart_count += 1
                if self.start(name):
                    restarted.append(name)
                    try:
                        from kernel.decision_log import record_decision
                        record_decision(
                            "service_manager",
                            "service_restart",
                            name,
                            "restarted",
                            f"exit={code}, count={svc.restart_count}",
                        )
                    except Exception:
                        pass
        return restarted

    def status(self) -> dict[str, Any]:
        services = {}
        for name, svc in self._services.items():
            uptime = None
            if svc.started_at and svc.state == ServiceState.RUNNING:
                uptime = round(time.time() - svc.started_at, 1)
            services[name] = {
                "state": svc.state.value,
                "ipc": svc.spec.ipc,
                "autostart": svc.spec.autostart,
                "restart_count": svc.restart_count,
                "uptime_s": uptime,
                "last_error": svc.last_error,
                "pid": svc.proc.pid if svc.proc and svc.proc.poll() is None else None,
            }
        return {"services": services, "count": len(services)}

    def _require(self, name: str) -> ManagedService:
        if name not in self._services:
            raise KeyError(f"unknown service: {name}")
        return self._services[name]

    def _stop_process(self, svc: ManagedService) -> None:
        if svc.client:
            try:
                svc.client.close()
            except Exception:
                pass
            svc.client = None
        if svc.proc and svc.proc.poll() is None:
            svc.proc.terminate()
            try:
                svc.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                svc.proc.kill()
        svc.proc = None

    def _mark_crashed(self, svc: ManagedService, reason: str) -> None:
        svc.state = ServiceState.CRASHED
        svc.last_error = reason
        self._stop_process(svc)
        self.bus.publish("service.crashed", {"name": svc.spec.name, "error": reason})


def default_services() -> list[ServiceSpec]:
    py = sys.executable
    return [
        ServiceSpec(
            name="code-worker",
            command=[py, "-m", "agents.code.subprocess_runner"],
            autostart=True,
            ipc=True,
            description="Isolated code execution worker",
        ),
    ]
