"""
runtime/acme_renewal_timer.py
=============================
Automated Let's Encrypt *renewal timer* foundation (ADR-038).

Default-off. Periodically invokes an ``AcmeProductionClient.issue`` (or
soft ``certbot renew``) on an interval thread. CI uses a Fake clock /
manual ``tick()`` without sleeping.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from runtime.acme_account import _truthy
from runtime.acme_production import AcmeProductionClient


class AcmeRenewalError(RuntimeError):
    """ACME renewal timer failed."""


RenewFn = Callable[[], dict[str, Any]]


@dataclass
class AcmeRenewalConfig:
    enabled: bool = False
    interval_s: float = 3600.0
    allow_live: bool = False
    use_certbot_renew: bool = False
    certbot_bin: str = "certbot"
    autostart: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "AcmeRenewalConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_RENEWAL")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        interval = data.get("interval_s", 3600.0)
        env_i = os.environ.get("KERROS_ACTOR_MESH_ACME_RENEWAL_INTERVAL")
        if env_i is not None:
            interval = float(env_i)

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_ACME_RENEWAL_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        use_cb = data.get("use_certbot_renew", False)
        env_c = os.environ.get("KERROS_ACTOR_MESH_ACME_RENEWAL_CERTBOT")
        if env_c is not None:
            use_cb = _truthy(env_c)
        else:
            use_cb = _truthy(use_cb)

        autostart = data.get("autostart", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_ACME_RENEWAL_AUTOSTART")
        if env_a is not None:
            autostart = _truthy(env_a)
        else:
            autostart = _truthy(autostart)

        return cls(
            enabled=bool(enabled),
            interval_s=max(1.0, float(interval or 3600.0)),
            allow_live=bool(allow_live),
            use_certbot_renew=bool(use_cb),
            certbot_bin=str(
                os.environ.get("KERROS_ACTOR_MESH_ACME_CERTBOT")
                or data.get("certbot_bin")
                or "certbot"
            ).strip()
            or "certbot",
            autostart=bool(autostart),
        )


def soft_certbot_renew(
    *,
    bin_name: str = "certbot",
    dry_run: bool = True,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    path = shutil.which(bin_name)
    if not path:
        return {"ok": False, "skipped": True, "error": f"{bin_name} not on PATH"}
    cmd = [path, "renew"]
    if dry_run:
        cmd.append("--dry-run")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-2000:],
            "dry_run": dry_run,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@dataclass
class AcmeRenewalTimer:
    """Interval renewal driver with manual tick for tests."""

    cfg: AcmeRenewalConfig
    production: AcmeProductionClient | None = None
    renew_fn: RenewFn | None = None
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _ticks: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def tick(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise AcmeRenewalError("ACME renewal timer disabled")
        if self.renew_fn is not None:
            out = self.renew_fn()
        elif self.cfg.use_certbot_renew:
            out = soft_certbot_renew(
                bin_name=self.cfg.certbot_bin,
                dry_run=not self.cfg.allow_live,
            )
        elif self.production is not None:
            out = self.production.issue()
        else:
            out = {"ok": True, "skipped": True, "error": "no renew backend"}
        with self._lock:
            self._ticks += 1
            self._last = dict(out)
            self._last["tick"] = self._ticks
            self._last["at"] = time.time()
        return dict(self._last)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(self.cfg.interval_s):
                try:
                    self.tick()
                except Exception as exc:
                    with self._lock:
                        self._last = {"ok": False, "error": str(exc)}

        self._thread = threading.Thread(
            target=_loop, name="acme-renewal-timer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "interval_s": self.cfg.interval_s,
                "allow_live": self.cfg.allow_live,
                "use_certbot_renew": self.cfg.use_certbot_renew,
                "running": self._thread is not None,
                "ticks": self._ticks,
                "last": dict(self._last),
            }


def build_acme_renewal_timer(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    production: AcmeProductionClient | None = None,
    renew_fn: RenewFn | None = None,
) -> AcmeRenewalTimer | None:
    rcfg = AcmeRenewalConfig.from_mapping(cfg)
    if not rcfg.enabled:
        return None
    timer = AcmeRenewalTimer(
        cfg=rcfg, production=production, renew_fn=renew_fn
    )
    if rcfg.autostart:
        timer.start()
    return timer
