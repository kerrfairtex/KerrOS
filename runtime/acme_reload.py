"""
runtime/acme_reload.py
======================
ACME / Let's Encrypt cert watch + TLS reload foundation (ADR-029).

Default-off. Watches an ACME ``live/<name>/`` directory (fullchain.pem +
privkey.pem) and triggers ``ReloadingTlsHolder.reload`` when mtimes change.
Optional soft ``certbot renew --dry-run`` probe (never required).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from runtime.actor_mesh_tls import MeshTlsConfig, ReloadingTlsHolder, _truthy


class AcmeError(RuntimeError):
    """ACME watch / renew helper failed."""


@dataclass
class AcmeConfig:
    enabled: bool = False
    live_dir: str = ""  # e.g. /etc/letsencrypt/live/example.com
    domain: str = ""
    fullchain_name: str = "fullchain.pem"
    privkey_name: str = "privkey.pem"
    chain_name: str = "chain.pem"  # optional CA
    watch_interval_s: float = 60.0
    certbot_bin: str = "certbot"
    allow_certbot_probe: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "AcmeConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        live = os.environ.get("KERROS_ACTOR_MESH_ACME_LIVE")
        if live is None:
            live = str(data.get("live_dir") or "")
        domain = os.environ.get("KERROS_ACTOR_MESH_ACME_DOMAIN")
        if domain is None:
            domain = str(data.get("domain") or "")
        domain = str(domain or "").strip()

        live_path = Path(live) if live else Path("")
        if live and not live_path.is_absolute() and base is not None:
            live_path = Path(base) / live_path
        # If live_dir points at .../live and domain set, append domain.
        if live and domain and live_path.name == "live":
            live_path = live_path / domain

        interval = data.get("watch_interval_s", 60.0)
        env_i = os.environ.get("KERROS_ACTOR_MESH_ACME_INTERVAL")
        if env_i is not None:
            interval = float(env_i)

        probe = data.get("allow_certbot_probe", False)
        env_p = os.environ.get("KERROS_ACTOR_MESH_ACME_CERTBOT_PROBE")
        if env_p is not None:
            probe = _truthy(env_p)
        else:
            probe = _truthy(probe)

        return cls(
            enabled=bool(enabled),
            live_dir=str(live_path) if live else "",
            domain=domain,
            fullchain_name=str(data.get("fullchain_name") or "fullchain.pem"),
            privkey_name=str(data.get("privkey_name") or "privkey.pem"),
            chain_name=str(data.get("chain_name") or "chain.pem"),
            watch_interval_s=max(0.0, float(interval or 0.0)),
            certbot_bin=str(
                os.environ.get("KERROS_ACTOR_MESH_ACME_CERTBOT")
                or data.get("certbot_bin")
                or "certbot"
            ).strip()
            or "certbot",
            allow_certbot_probe=bool(probe),
        )


def resolve_acme_paths(cfg: AcmeConfig) -> dict[str, Path]:
    root = Path(cfg.live_dir)
    return {
        "fullchain": root / cfg.fullchain_name,
        "privkey": root / cfg.privkey_name,
        "chain": root / cfg.chain_name,
    }


def acme_paths_to_tls_config(
    cfg: AcmeConfig,
    *,
    require_client_cert: bool = False,
    check_hostname: bool = False,
    reload: bool = True,
) -> MeshTlsConfig:
    paths = resolve_acme_paths(cfg)
    ca = paths["chain"] if paths["chain"].is_file() else paths["fullchain"]
    return MeshTlsConfig(
        enabled=True,
        ca_file=str(ca) if ca.is_file() else "",
        cert_file=str(paths["fullchain"]),
        key_file=str(paths["privkey"]),
        require_client_cert=require_client_cert,
        check_hostname=check_hostname,
        reload=reload,
        reload_interval_s=cfg.watch_interval_s,
    )


def pem_mtimes_for_acme(cfg: AcmeConfig) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, path in resolve_acme_paths(cfg).items():
        try:
            out[key] = float(path.stat().st_mtime) if path.is_file() else 0.0
        except OSError:
            out[key] = 0.0
    return out


def certbot_available(bin_name: str = "certbot") -> bool:
    return shutil.which(bin_name) is not None


def probe_certbot_renew(
    *,
    bin_name: str = "certbot",
    dry_run: bool = True,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """
    Soft certbot renew probe. Never raises into callers that catch AcmeError.
    """
    if not certbot_available(bin_name):
        return {"ok": False, "error": f"{bin_name} not on PATH", "skipped": True}
    cmd = [bin_name, "renew"]
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
class AcmeCertWatcher:
    """
    Poll ACME live dir and reload TLS holder when PEMs change.
    """

    cfg: AcmeConfig
    tls_holder: ReloadingTlsHolder | None = None
    _mtimes: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _reloads: int = 0
    _last_check: float = 0.0
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)

    def bind_tls_holder(self, holder: ReloadingTlsHolder) -> None:
        self.tls_holder = holder

    def check_once(self) -> bool:
        """Return True if certs changed and TLS holder reloaded."""
        if not self.cfg.enabled:
            return False
        paths = resolve_acme_paths(self.cfg)
        if not paths["fullchain"].is_file() or not paths["privkey"].is_file():
            return False
        now_m = pem_mtimes_for_acme(self.cfg)
        with self._lock:
            first = not self._mtimes
            changed = now_m != self._mtimes
            self._last_check = time.time()
            if not changed:
                return False
            self._mtimes = now_m

        if self.tls_holder is None:
            return False
        self.tls_holder.cfg = acme_paths_to_tls_config(self.cfg)
        reloaded = self.tls_holder.reload(force=True)
        if reloaded and not first:
            with self._lock:
                self._reloads += 1
            return True
        return False

    def start_watch(self) -> None:
        if not self.cfg.enabled or self._thread is not None:
            return
        self._stop.clear()
        interval = max(0.05, float(self.cfg.watch_interval_s or 60.0))

        def _loop() -> None:
            while not self._stop.wait(interval):
                try:
                    self.check_once()
                except Exception:
                    pass

        self._thread = threading.Thread(
            target=_loop, name="acme-cert-watch", daemon=True
        )
        self._thread.start()

    def stop_watch(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def maybe_probe_certbot(self) -> dict[str, Any]:
        if not self.cfg.allow_certbot_probe:
            return {"ok": False, "skipped": True, "reason": "probe disabled"}
        return probe_certbot_renew(bin_name=self.cfg.certbot_bin, dry_run=True)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "live_dir": self.cfg.live_dir,
                "domain": self.cfg.domain,
                "reloads": self._reloads,
                "mtimes": dict(self._mtimes),
                "watching": self._thread is not None,
                "certbot_on_path": certbot_available(self.cfg.certbot_bin),
            }
