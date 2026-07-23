"""
runtime/kerrd.py
==============
kerrd — KerrOS service daemon (Phase 2).

Boots the kernel, manages services, and runs health monitoring.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.health import HealthMonitor
from runtime.service_bus import ServiceBus
from runtime.services import ServiceManager, default_services

PID_FILE = ROOT / "data" / "kerrd.pid"


class Kerrd:
    def __init__(self) -> None:
        self.bus = ServiceBus()
        self.services = ServiceManager(self.bus)
        self.health = HealthMonitor()
        self._running = False

        for spec in default_services():
            self.services.register(spec)

        self.bus.subscribe("service.crashed", self._on_service_crashed)

    def _on_service_crashed(self, payload: dict) -> None:
        self.health.record(
            "service",
            "crashed",
            f"{payload.get('name')}: {payload.get('error', '')}",
        )

    def start(self, *, foreground: bool = True, interval: float = 5.0) -> int:
        from kernel.boot import boot
        from kernel.decision_log import record_decision

        boot()
        record_decision(
            "kerrd",
            "daemon",
            "kerrd.start",
            "started",
            "",
        )

        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

        started = self.services.start_autostart()
        self.health.record("kerrd", "ok", f"autostart={started}")
        self._running = True

        if not foreground:
            return 0

        print(f"[kerrd] running — services: {', '.join(started) or 'none'}")
        try:
            while self._running:
                restarted = self.services.monitor()
                if restarted:
                    print(f"[kerrd] restarted: {', '.join(restarted)}")
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
        return 0

    def stop(self) -> None:
        self._running = False
        for name in list(self.services._services.keys()):
            self.services.stop(name)
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        try:
            from kernel.decision_log import record_decision
            record_decision("kerrd", "daemon", "kerrd.stop", "stopped", "")
        except Exception:
            pass

    def status(self) -> dict:
        from kernel.boot import get_kernel

        return {
            "pid_file": str(PID_FILE),
            "pid": int(PID_FILE.read_text()) if PID_FILE.exists() else None,
            "kernel": get_kernel().status(),
            "services": self.services.status(),
        }

    def health_report(self) -> dict:
        return self.health.collect(self.services)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kerrd", description="KerrOS service daemon")
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=["start", "stop", "status", "health", "restart-service"],
    )
    parser.add_argument("--interval", type=float, default=5.0, help="Health poll interval (seconds)")
    parser.add_argument("--service", help="Service name for restart-service")
    args = parser.parse_args(argv)

    kerrd = Kerrd()

    if args.command == "start":
        if "--watchdog" in (argv or sys.argv):
            from kernel.watchdog import supervise
            supervise([sys.executable, str(ROOT / "kerrd"), "start", f"--interval={args.interval}"])
            return 0
        return kerrd.start(interval=args.interval)

    if args.command == "stop":
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                PID_FILE.unlink(missing_ok=True)
            print(f"[kerrd] stop signal sent to pid {pid}")
        else:
            print("[kerrd] not running")
        return 0

    if args.command == "status":
        import json
        boot()
        print(json.dumps(kerrd.status(), indent=2))
        return 0

    if args.command == "health":
        boot()
        import json
        print(json.dumps(kerrd.health_report(), indent=2))
        return 0

    if args.command == "restart-service":
        boot()
        if not args.service:
            print("error: --service required")
            return 1
        ok = kerrd.services.restart(args.service)
        print(f"[kerrd] restart {args.service}: {'ok' if ok else 'failed'}")
        return 0 if ok else 1

    return 1


def boot():
    from kernel.boot import boot as kernel_boot
    return kernel_boot()
