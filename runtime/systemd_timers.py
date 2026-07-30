"""
runtime/systemd_timers.py
=========================
systemd unit/timer packaging foundation (ADR-039).

Default-off. Renders ``kerros-acme-renew.service`` + ``.timer`` unit
text and optionally writes them under a units directory (never touches
``/etc/systemd`` unless ``allow_install`` and an explicit install root).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from runtime.nats_supercluster import _truthy


class SystemdTimerError(RuntimeError):
    """systemd timer packaging failed."""


SERVICE_TEMPLATE = """\
[Unit]
Description=KerrOS ACME certificate renewal ({org})
Documentation=https://github.com/kerrfairtex/KerrOS
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={workdir}
Environment=KERROS_ACTOR_MESH_ACME_PRODUCTION=1
Environment=KERROS_ACTOR_MESH_ACME_PRODUCTION_TOOL={tool}
ExecStart={exec_start}
Nice=10

[Install]
WantedBy=multi-user.target
"""

TIMER_TEMPLATE = """\
[Unit]
Description=KerrOS ACME renewal timer ({org})
Documentation=https://github.com/kerrfairtex/KerrOS

[Timer]
OnCalendar={on_calendar}
Persistent=true
RandomizedDelaySec={random_delay}

[Install]
WantedBy=timers.target
"""


@dataclass
class SystemdTimerConfig:
    enabled: bool = False
    org_name: str = "KerrOS"
    workdir: str = ""
    exec_start: str = "python3 -m runtime.acme_production"
    tool: str = "fake"
    on_calendar: str = "daily"
    random_delay: str = "15m"
    units_dir: str = "deploy/systemd"
    allow_write: bool = False
    allow_install: bool = False
    install_root: str = ""  # e.g. /etc/systemd/system — gated
    unit_basename: str = "kerros-acme-renew"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "SystemdTimerConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_TIMERS")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        org = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_ORG")
        if org is None:
            org = str(data.get("org_name") or "KerrOS")

        workdir = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_WORKDIR")
        if workdir is None:
            workdir = str(data.get("workdir") or "")
        if not workdir and base is not None:
            workdir = str(base)

        exec_start = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_EXEC")
        if exec_start is None:
            exec_start = str(
                data.get("exec_start") or "python3 -c \"print('kerros-acme-renew')\""
            )

        tool = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION_TOOL")
        if tool is None:
            tool = str(data.get("tool") or "fake")

        calendar = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_CALENDAR")
        if calendar is None:
            calendar = str(data.get("on_calendar") or "daily")

        delay = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_DELAY")
        if delay is None:
            delay = str(data.get("random_delay") or "15m")

        units_dir = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_UNITS_DIR")
        if units_dir is None:
            units_dir = str(data.get("units_dir") or "deploy/systemd")
        units_path = Path(units_dir)
        if not units_path.is_absolute() and base is not None:
            units_path = Path(base) / units_path

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_install = data.get("allow_install", False)
        env_i = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_INSTALL")
        if env_i is not None:
            allow_install = _truthy(env_i)
        else:
            allow_install = _truthy(allow_install)

        install_root = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_INSTALL_ROOT")
        if install_root is None:
            install_root = str(data.get("install_root") or "")

        basename = os.environ.get("KERROS_ACTOR_MESH_SYSTEMD_BASENAME")
        if basename is None:
            basename = str(data.get("unit_basename") or "kerros-acme-renew")

        return cls(
            enabled=bool(enabled),
            org_name=str(org or "KerrOS").strip() or "KerrOS",
            workdir=str(workdir or "").strip(),
            exec_start=str(exec_start or "").strip(),
            tool=str(tool or "fake").strip() or "fake",
            on_calendar=str(calendar or "daily").strip() or "daily",
            random_delay=str(delay or "15m").strip() or "15m",
            units_dir=str(units_path),
            allow_write=bool(allow_write),
            allow_install=bool(allow_install),
            install_root=str(install_root or "").strip(),
            unit_basename=str(basename or "kerros-acme-renew").strip()
            or "kerros-acme-renew",
        )


@dataclass
class SystemdTimerPackager:
    """Render and optionally write/install systemd units."""

    cfg: SystemdTimerConfig
    _last_write: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def render_service(self) -> str:
        return SERVICE_TEMPLATE.format(
            org=self.cfg.org_name,
            workdir=self.cfg.workdir or "/opt/kerros",
            tool=self.cfg.tool,
            exec_start=self.cfg.exec_start,
        )

    def render_timer(self) -> str:
        return TIMER_TEMPLATE.format(
            org=self.cfg.org_name,
            on_calendar=self.cfg.on_calendar,
            random_delay=self.cfg.random_delay,
        )

    def write_units(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise SystemdTimerError("systemd timers disabled")
        if not self.cfg.allow_write:
            return {
                "ok": False,
                "skipped": True,
                "error": "write disabled",
                "service": self.render_service(),
                "timer": self.render_timer(),
            }
        root = Path(self.cfg.units_dir)
        root.mkdir(parents=True, exist_ok=True)
        service_path = root / f"{self.cfg.unit_basename}.service"
        timer_path = root / f"{self.cfg.unit_basename}.timer"
        service_path.write_text(self.render_service(), encoding="utf-8")
        timer_path.write_text(self.render_timer(), encoding="utf-8")
        out = {
            "ok": True,
            "service_path": str(service_path),
            "timer_path": str(timer_path),
        }
        with self._lock:
            self._last_write = dict(out)
        return out

    def install_units(self) -> dict[str, Any]:
        """
        Copy rendered units to install_root when allow_install.
        Never defaults to /etc — requires explicit install_root.
        """
        if not self.cfg.allow_install:
            return {"ok": False, "skipped": True, "error": "install disabled"}
        if not self.cfg.install_root:
            return {"ok": False, "error": "install_root required"}
        written = self.write_units()
        if not written.get("ok"):
            # Force write for install path when allow_write was off.
            root = Path(self.cfg.units_dir)
            root.mkdir(parents=True, exist_ok=True)
            service_path = root / f"{self.cfg.unit_basename}.service"
            timer_path = root / f"{self.cfg.unit_basename}.timer"
            service_path.write_text(self.render_service(), encoding="utf-8")
            timer_path.write_text(self.render_timer(), encoding="utf-8")
            written = {
                "ok": True,
                "service_path": str(service_path),
                "timer_path": str(timer_path),
            }
        dest = Path(self.cfg.install_root)
        dest.mkdir(parents=True, exist_ok=True)
        for key in ("service_path", "timer_path"):
            src = Path(written[key])
            shutil.copy2(src, dest / src.name)
        out = {
            "ok": True,
            "install_root": str(dest),
            "copied": [
                str(dest / f"{self.cfg.unit_basename}.service"),
                str(dest / f"{self.cfg.unit_basename}.timer"),
            ],
        }
        # Soft systemctl daemon-reload probe — never required.
        systemctl = shutil.which("systemctl")
        if systemctl:
            try:
                proc = subprocess.run(
                    [systemctl, "daemon-reload"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                )
                out["daemon_reload"] = {
                    "ok": proc.returncode == 0,
                    "returncode": proc.returncode,
                }
            except Exception as exc:
                out["daemon_reload"] = {"ok": False, "error": str(exc)}
        else:
            out["daemon_reload"] = {"ok": False, "skipped": True}
        with self._lock:
            self._last_write = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "allow_write": self.cfg.allow_write,
                "allow_install": self.cfg.allow_install,
                "units_dir": self.cfg.units_dir,
                "unit_basename": self.cfg.unit_basename,
                "on_calendar": self.cfg.on_calendar,
                "last": dict(self._last_write),
            }


def build_systemd_timer_packager(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> SystemdTimerPackager | None:
    scfg = SystemdTimerConfig.from_mapping(cfg, base=base)
    if not scfg.enabled:
        return None
    packager = SystemdTimerPackager(cfg=scfg)
    if scfg.allow_write:
        try:
            packager.write_units()
        except Exception:
            pass
    return packager
