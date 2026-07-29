"""
runtime/health.py
=================
Health monitoring for KerrOS runtime (Phase 2).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthMonitor:
    started_at: float = field(default_factory=time.time)
    checks: list[dict[str, Any]] = field(default_factory=list)
    _history: list[dict[str, Any]] = field(default_factory=list)

    def record(self, component: str, status: str, detail: str = "") -> None:
        entry = {
            "time": time.time(),
            "component": component,
            "status": status,
            "detail": detail,
        }
        self.checks.append(entry)
        self._history.append(entry)
        if len(self._history) > 200:
            self._history = self._history[-200:]

    def collect(self, service_manager=None) -> dict[str, Any]:
        report: dict[str, Any] = {
            "uptime_s": round(time.time() - self.started_at, 1),
            "healthy": True,
            "components": {},
        }

        try:
            from kernel.boot import get_kernel
            from kernel.contract import BootPhase

            kernel = get_kernel()
            k_status = kernel.status()
            k_ok = kernel.phase == BootPhase.READY
            report["components"]["kernel"] = {
                "status": "ok" if k_ok else "degraded",
                "phase": k_status.get("phase"),
                "services": k_status.get("services", []),
            }
            self.record("kernel", "ok" if k_ok else "degraded", k_status.get("phase", ""))
            if not k_ok:
                report["healthy"] = False
        except Exception as exc:
            report["components"]["kernel"] = {"status": "error", "error": str(exc)}
            report["healthy"] = False
            self.record("kernel", "error", str(exc))

        if service_manager is not None:
            sm = service_manager.status()
            running = sum(
                1 for s in sm["services"].values() if s["state"] == "running"
            )
            crashed = sum(
                1 for s in sm["services"].values() if s["state"] == "crashed"
            )
            sm_ok = crashed == 0
            report["components"]["services"] = {
                "status": "ok" if sm_ok else "degraded",
                "running": running,
                "crashed": crashed,
                "details": sm["services"],
            }
            self.record("services", "ok" if sm_ok else "degraded", f"running={running}")
            if not sm_ok:
                report["healthy"] = False

        try:
            from kernel.decision_log import get_decision_log

            log = get_decision_log()
            report["components"]["decision_log"] = {
                "status": "ok",
                "entries": log.count(),
            }
            self.record("decision_log", "ok", str(log.count()))
        except Exception as exc:
            report["components"]["decision_log"] = {"status": "error", "error": str(exc)}
            self.record("decision_log", "error", str(exc))

        try:
            from kernel.boot import resolve as kernel_resolve

            bus = kernel_resolve("event_bus")
            sched = kernel_resolve("scheduler")
            report["components"]["event_bus"] = {
                "status": "ok",
                "events": bus.stats().get("events", 0),
            }
            report["components"]["scheduler"] = {
                "status": "ok",
                "jobs": len(sched.list_jobs()),
            }
            self.record("event_bus", "ok", str(bus.stats().get("events", 0)))
        except Exception as exc:
            report["components"]["event_bus"] = {"status": "error", "error": str(exc)}
            self.record("event_bus", "error", str(exc))

        try:
            from adapters.llm.omniroute_adapter import probe_omniroute

            omni = probe_omniroute()
            report["components"]["omniroute"] = omni
            self.record(
                "omniroute",
                omni.get("status", "unknown"),
                omni.get("base_url", ""),
            )
            # Optional gateway: only fail overall health when enabled but down.
            if omni.get("enabled") and omni.get("status") != "ok":
                report["healthy"] = False
        except Exception as exc:
            report["components"]["omniroute"] = {
                "status": "error",
                "provider": "omniroute",
                "error": str(exc),
            }
            self.record("omniroute", "error", str(exc))

        try:
            from adapters.memory.qdrant_vector_store import probe_qdrant

            qdrant = probe_qdrant()
            report["components"]["qdrant"] = qdrant
            self.record(
                "qdrant",
                qdrant.get("status", "unknown"),
                qdrant.get("base_url", ""),
            )
            # Optional vector sidecar: only fail overall when enabled but down.
            if qdrant.get("enabled") and qdrant.get("status") != "ok":
                report["healthy"] = False
        except Exception as exc:
            report["components"]["qdrant"] = {
                "status": "error",
                "component": "qdrant",
                "error": str(exc),
            }
            self.record("qdrant", "error", str(exc))

        return report

    def summary(self, service_manager=None) -> str:
        report = self.collect(service_manager)
        lines = [
            f"healthy={report['healthy']} uptime={report['uptime_s']}s",
        ]
        for name, comp in report["components"].items():
            lines.append(f"  {name}: {comp.get('status', 'unknown')}")
        return "\n".join(lines)
