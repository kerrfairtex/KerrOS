"""
runtime/acme_production.py
==========================
Packaged *production* ACME runner foundation (ADR-037).

Default-off. Soft-wraps ``certbot`` / ``acme.sh`` style issuance and
installs resulting PEMs into an ACME live-dir layout for ADR-029 watch.
CI uses ``FakePackagedAcme`` (writes stub PEMs; no network).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from runtime.acme_account import _truthy


class AcmeProductionError(RuntimeError):
    """Packaged production ACME failed."""


@runtime_checkable
class PackagedAcmeRunner(Protocol):
    def issue(self, domains: list[str], *, email: str = "", live_dir: str = "") -> dict[str, Any]: ...

    def stats(self) -> dict[str, Any]: ...


def _write_stub_pem(path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"-----BEGIN {label}-----\nKERROS-FAKE-{label}\n-----END {label}-----\n",
        encoding="utf-8",
    )


@dataclass
class FakePackagedAcme:
    """CI-safe packaged ACME that writes stub PEMs into live_dir."""

    tool: str = "fake"
    _issues: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def issue(self, domains: list[str], *, email: str = "", live_dir: str = "") -> dict[str, Any]:
        names = [str(d).strip() for d in domains if str(d).strip()]
        if not names:
            raise AcmeProductionError("at least one domain required")
        primary = names[0]
        base = Path(live_dir) if live_dir else Path("data/acme_live")
        # Let's Encrypt-style live/<domain>/ when base is .../live or a parent dir.
        if base.name == "live" or not live_dir:
            root = (base if base.name == "live" else Path("data/acme_live")) / primary
        elif base.name == primary:
            root = base
        else:
            root = base / primary
        root.mkdir(parents=True, exist_ok=True)
        fullchain = root / "fullchain.pem"
        privkey = root / "privkey.pem"
        chain = root / "chain.pem"
        _write_stub_pem(fullchain, "CERTIFICATE")
        _write_stub_pem(privkey, "PRIVATE KEY")
        _write_stub_pem(chain, "CERTIFICATE")
        with self._lock:
            self._issues += 1
        return {
            "ok": True,
            "fake": True,
            "tool": self.tool,
            "domains": names,
            "email": email,
            "live_dir": str(root),
            "fullchain": str(fullchain),
            "privkey": str(privkey),
            "chain": str(chain),
            "issued_at": time.time(),
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"tool": self.tool, "issues": self._issues, "backend": "fake"}


@dataclass
class SoftCertbotRunner:
    """Soft ``certbot certonly`` wrapper when allow_live and binary present."""

    bin_name: str = "certbot"
    allow_live: bool = False
    staging: bool = True
    timeout_s: float = 120.0
    _shadow: FakePackagedAcme = field(default_factory=lambda: FakePackagedAcme(tool="certbot"))
    _last: dict[str, Any] = field(default_factory=dict)

    def issue(self, domains: list[str], *, email: str = "", live_dir: str = "") -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.issue(domains, email=email, live_dir=live_dir)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        path = shutil.which(self.bin_name)
        if not path:
            out = {"ok": False, "skipped": True, "error": f"{self.bin_name} not on PATH"}
            self._last = dict(out)
            return out
        names = [str(d).strip() for d in domains if str(d).strip()]
        cmd = [path, "certonly", "--non-interactive", "--agree-tos"]
        if self.staging:
            cmd.append("--staging")
        if email:
            cmd.extend(["--email", email])
        else:
            cmd.append("--register-unsafely-without-email")
        for d in names:
            cmd.extend(["-d", d])
        # Prefer webroot/dns plugins externally; here use standalone soft attempt.
        cmd.extend(["--preferred-challenges", "dns", "--manual"])
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
                "stdout": (proc.stdout or "")[-2000:],
                "stderr": (proc.stderr or "")[-2000:],
                "tool": "certbot",
                "domains": names,
                "staging": self.staging,
            }
            self._last = dict(out)
            return out
        except Exception as exc:
            out = {"ok": False, "error": str(exc), "tool": "certbot"}
            self._last = dict(out)
            return out

    def stats(self) -> dict[str, Any]:
        return {
            "tool": "certbot",
            "allow_live": self.allow_live,
            "staging": self.staging,
            "available": shutil.which(self.bin_name) is not None,
            "last": dict(self._last),
        }


@dataclass
class SoftAcmeShRunner:
    """Soft ``acme.sh --issue`` wrapper when allow_live."""

    bin_name: str = "acme.sh"
    allow_live: bool = False
    staging: bool = True
    timeout_s: float = 120.0
    _shadow: FakePackagedAcme = field(default_factory=lambda: FakePackagedAcme(tool="acme.sh"))
    _last: dict[str, Any] = field(default_factory=dict)

    def issue(self, domains: list[str], *, email: str = "", live_dir: str = "") -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.issue(domains, email=email, live_dir=live_dir)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        path = shutil.which(self.bin_name)
        if not path:
            # Common install location
            home = Path.home() / ".acme.sh" / "acme.sh"
            path = str(home) if home.is_file() else None
        if not path:
            out = {"ok": False, "skipped": True, "error": "acme.sh not found"}
            self._last = dict(out)
            return out
        names = [str(d).strip() for d in domains if str(d).strip()]
        cmd = [path, "--issue"]
        if self.staging:
            cmd.append("--staging")
        for d in names:
            cmd.extend(["-d", d])
        if email:
            cmd.extend(["--accountemail", email])
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
                "stdout": (proc.stdout or "")[-2000:],
                "stderr": (proc.stderr or "")[-2000:],
                "tool": "acme.sh",
                "domains": names,
                "staging": self.staging,
            }
            self._last = dict(out)
            return out
        except Exception as exc:
            out = {"ok": False, "error": str(exc), "tool": "acme.sh"}
            self._last = dict(out)
            return out

    def stats(self) -> dict[str, Any]:
        return {
            "tool": "acme.sh",
            "allow_live": self.allow_live,
            "staging": self.staging,
            "last": dict(self._last),
        }


@dataclass
class AcmeProductionConfig:
    enabled: bool = False
    tool: str = "fake"  # fake | certbot | acme.sh
    allow_live: bool = False
    staging: bool = True
    domains: list[str] = field(default_factory=list)
    email: str = ""
    live_dir: str = "data/acme_live"
    auto_issue: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "AcmeProductionConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        tool = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION_TOOL")
        if tool is None:
            tool = str(data.get("tool") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        staging = data.get("staging", True)
        env_s = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION_STAGING")
        if env_s is not None:
            staging = _truthy(env_s)
        elif not isinstance(staging, bool):
            staging = _truthy(staging)

        domains_raw = data.get("domains") or []
        env_d = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION_DOMAINS")
        if env_d is not None:
            domains = [d.strip() for d in env_d.split(",") if d.strip()]
        elif isinstance(domains_raw, str):
            domains = [d.strip() for d in domains_raw.split(",") if d.strip()]
        else:
            domains = [str(d).strip() for d in domains_raw if str(d).strip()]

        email = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION_EMAIL")
        if email is None:
            email = str(data.get("email") or "")

        live = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION_LIVE_DIR")
        if live is None:
            live = str(data.get("live_dir") or "data/acme_live")
        live_path = Path(live)
        if not live_path.is_absolute() and base is not None:
            live_path = Path(base) / live_path

        auto_issue = data.get("auto_issue", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_ACME_PRODUCTION_AUTO")
        if env_a is not None:
            auto_issue = _truthy(env_a)
        else:
            auto_issue = _truthy(auto_issue)

        return cls(
            enabled=bool(enabled),
            tool=str(tool or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            staging=bool(staging),
            domains=domains,
            email=str(email or "").strip(),
            live_dir=str(live_path),
            auto_issue=bool(auto_issue),
        )


@dataclass
class AcmeProductionClient:
    """Packaged ACME issue + install facade."""

    cfg: AcmeProductionConfig
    runner: PackagedAcmeRunner = field(default_factory=FakePackagedAcme)
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def issue(self, domains: Optional[list[str]] = None) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise AcmeProductionError("ACME production runner disabled")
        names = list(domains or self.cfg.domains)
        out = self.runner.issue(
            names, email=self.cfg.email, live_dir=self.cfg.live_dir
        )
        with self._lock:
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "tool": self.cfg.tool,
                "allow_live": self.cfg.allow_live,
                "staging": self.cfg.staging,
                "domains": list(self.cfg.domains),
                "live_dir": self.cfg.live_dir,
                "auto_issue": self.cfg.auto_issue,
                "last": dict(self._last),
                "runner": self.runner.stats(),
            }


def build_acme_production_client(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    runner: PackagedAcmeRunner | None = None,
    base: Optional[Path] = None,
) -> AcmeProductionClient | None:
    prod_cfg = AcmeProductionConfig.from_mapping(cfg, base=base)
    if not prod_cfg.enabled:
        return None
    if runner is not None:
        r = runner
    elif prod_cfg.tool in ("certbot",):
        r = SoftCertbotRunner(
            allow_live=prod_cfg.allow_live, staging=prod_cfg.staging
        )
    elif prod_cfg.tool in ("acme.sh", "acmesh", "acme_sh"):
        r = SoftAcmeShRunner(
            allow_live=prod_cfg.allow_live, staging=prod_cfg.staging
        )
    else:
        r = FakePackagedAcme(tool="fake")
    client = AcmeProductionClient(cfg=prod_cfg, runner=r)
    if prod_cfg.auto_issue and prod_cfg.domains:
        try:
            client.issue()
        except Exception:
            pass
    return client
