"""
runtime/distro_publish.py
=========================
apt/yum repository publish foundation (ADR-042).

Default-off. Stages package metadata into a local repo tree and soft-
invokes ``reprepro`` / ``createrepo_c`` when allow_publish. Never pushes
to remote mirrors by default (allow_remote gated). Fake backend for CI.
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

from runtime.distro_packages import DistroPackageConfig, render_deb_control, render_rpm_spec
from runtime.nats_supercluster import _truthy


class DistroPublishError(RuntimeError):
    """Distro repository publish failed."""


def reprepro_available() -> bool:
    return bool(shutil.which("reprepro"))


def createrepo_available() -> bool:
    return bool(shutil.which("createrepo_c") or shutil.which("createrepo"))


@runtime_checkable
class RepoPublisher(Protocol):
    def publish(self, *, formats: list[str], staging: Path) -> dict[str, Any]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeRepoPublisher:
    """In-memory / local-tree publisher for CI."""

    _publishes: int = 0
    _last: dict[str, Any] = field(default_factory=dict)

    def publish(self, *, formats: list[str], staging: Path) -> dict[str, Any]:
        staging.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        if "deb" in formats or "apt" in formats:
            apt_dir = staging / "apt" / "conf"
            apt_dir.mkdir(parents=True, exist_ok=True)
            dists = staging / "apt" / "dists" / "stable" / "main" / "binary-all"
            dists.mkdir(parents=True, exist_ok=True)
            packages = dists / "Packages"
            packages.write_text("# Fake apt Packages index\n", encoding="utf-8")
            written.append(str(packages))
            conf = apt_dir / "distributions"
            conf.write_text(
                "Origin: KerrOS\nLabel: KerrOS\nCodename: stable\n"
                "Architectures: all\nComponents: main\n",
                encoding="utf-8",
            )
            written.append(str(conf))
        if "rpm" in formats or "yum" in formats:
            yum_dir = staging / "yum" / "repodata"
            yum_dir.mkdir(parents=True, exist_ok=True)
            primary = yum_dir / "primary.xml"
            primary.write_text(
                '<?xml version="1.0"?><metadata packages="0"/>\n',
                encoding="utf-8",
            )
            written.append(str(primary))
        out = {
            "ok": True,
            "backend": "fake",
            "written": written,
            "formats": list(formats),
            "staging": str(staging),
            "at": time.time(),
            "note": "local fake repo — not published to a mirror",
        }
        self._publishes += 1
        self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "fake",
            "publishes": self._publishes,
            "last": dict(self._last),
        }


@dataclass
class SoftRepreproPublisher:
    """Soft reprepro include when allow_publish + binary present."""

    allow_publish: bool = False
    _shadow: FakeRepoPublisher = field(default_factory=FakeRepoPublisher)
    _last: dict[str, Any] = field(default_factory=dict)

    def publish(self, *, formats: list[str], staging: Path) -> dict[str, Any]:
        if not self.allow_publish or not reprepro_available():
            out = self._shadow.publish(formats=formats, staging=staging)
            out["dry_run"] = True
            out["reprepro"] = reprepro_available()
            self._last = dict(out)
            return out
        apt_root = staging / "apt"
        apt_root.mkdir(parents=True, exist_ok=True)
        conf = apt_root / "conf"
        conf.mkdir(parents=True, exist_ok=True)
        dist = conf / "distributions"
        if not dist.is_file():
            dist.write_text(
                "Origin: KerrOS\nLabel: KerrOS\nCodename: stable\n"
                "Architectures: all\nComponents: main\n",
                encoding="utf-8",
            )
        # Without a real .deb artifact, export empty list as smoke
        proc = subprocess.run(
            ["reprepro", "-b", str(apt_root), "list", "stable"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        out = {
            "ok": proc.returncode == 0,
            "backend": "reprepro",
            "returncode": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", errors="replace")[:300],
            "staging": str(staging),
            "at": time.time(),
        }
        self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "reprepro",
            "allow_publish": self.allow_publish,
            "available": reprepro_available(),
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class SoftCreaterepoPublisher:
    """Soft createrepo_c when allow_publish + binary present."""

    allow_publish: bool = False
    _shadow: FakeRepoPublisher = field(default_factory=FakeRepoPublisher)
    _last: dict[str, Any] = field(default_factory=dict)

    def publish(self, *, formats: list[str], staging: Path) -> dict[str, Any]:
        if not self.allow_publish or not createrepo_available():
            out = self._shadow.publish(formats=formats, staging=staging)
            out["dry_run"] = True
            out["createrepo"] = createrepo_available()
            self._last = dict(out)
            return out
        yum_root = staging / "yum"
        yum_root.mkdir(parents=True, exist_ok=True)
        bin_name = "createrepo_c" if shutil.which("createrepo_c") else "createrepo"
        proc = subprocess.run(
            [bin_name, str(yum_root)],
            capture_output=True,
            timeout=60,
            check=False,
        )
        out = {
            "ok": proc.returncode == 0,
            "backend": bin_name,
            "returncode": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", errors="replace")[:300],
            "staging": str(staging),
            "at": time.time(),
        }
        self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "createrepo",
            "allow_publish": self.allow_publish,
            "available": createrepo_available(),
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class DistroPublishConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | reprepro | createrepo | auto
    formats: list[str] = field(default_factory=lambda: ["deb", "rpm"])
    staging_dir: str = "deploy/packaging/repos"
    package_name: str = "kerros"
    version: str = "0.1.0"
    allow_write: bool = False
    allow_publish: bool = False
    allow_remote: bool = False
    remote_url: str = ""

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "DistroPublishConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_DISTRO_PUBLISH")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_DISTRO_PUBLISH_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        formats_raw = data.get("formats") or ["deb", "rpm"]
        env_f = os.environ.get("KERROS_ACTOR_MESH_DISTRO_PUBLISH_FORMATS")
        if env_f is not None:
            formats = [s.strip().lower() for s in env_f.replace(",", " ").split() if s.strip()]
        elif isinstance(formats_raw, str):
            formats = [
                s.strip().lower()
                for s in formats_raw.replace(",", " ").split()
                if s.strip()
            ]
        else:
            formats = [str(s).strip().lower() for s in formats_raw if str(s).strip()]

        staging = os.environ.get("KERROS_ACTOR_MESH_DISTRO_PUBLISH_DIR")
        if staging is None:
            staging = str(data.get("staging_dir") or "deploy/packaging/repos")
        path = Path(staging)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        name = os.environ.get("KERROS_ACTOR_MESH_DISTRO_NAME")
        if name is None:
            name = str(data.get("package_name") or "kerros")

        version = os.environ.get("KERROS_ACTOR_MESH_DISTRO_VERSION")
        if version is None:
            version = str(data.get("version") or "0.1.0")

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_DISTRO_PUBLISH_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_publish = data.get("allow_publish", False)
        env_p = os.environ.get("KERROS_ACTOR_MESH_DISTRO_PUBLISH_LIVE")
        if env_p is not None:
            allow_publish = _truthy(env_p)
        else:
            allow_publish = _truthy(allow_publish)

        allow_remote = data.get("allow_remote", False)
        env_r = os.environ.get("KERROS_ACTOR_MESH_DISTRO_PUBLISH_REMOTE")
        if env_r is not None:
            allow_remote = _truthy(env_r)
        else:
            allow_remote = _truthy(allow_remote)

        remote_url = os.environ.get("KERROS_ACTOR_MESH_DISTRO_PUBLISH_URL")
        if remote_url is None:
            remote_url = str(data.get("remote_url") or "")

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            formats=formats or ["deb", "rpm"],
            staging_dir=str(path),
            package_name=str(name or "kerros").strip() or "kerros",
            version=str(version or "0.1.0").strip() or "0.1.0",
            allow_write=bool(allow_write),
            allow_publish=bool(allow_publish),
            allow_remote=bool(allow_remote),
            remote_url=str(remote_url or "").strip(),
        )


@dataclass
class DistroPublisher:
    """Stage and publish apt/yum repository metadata."""

    cfg: DistroPublishConfig
    publisher: RepoPublisher = field(default_factory=FakeRepoPublisher)
    _publishes: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def stage_metadata(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise DistroPublishError("distro publish disabled")
        preview = {
            "package_name": self.cfg.package_name,
            "version": self.cfg.version,
            "formats": list(self.cfg.formats),
        }
        pkg_cfg = DistroPackageConfig(
            enabled=True,
            package_name=self.cfg.package_name,
            version=self.cfg.version,
            formats=list(self.cfg.formats),
        )
        if "deb" in self.cfg.formats:
            preview["deb_control"] = render_deb_control(pkg_cfg)
        if "rpm" in self.cfg.formats:
            preview["rpm_spec"] = render_rpm_spec(pkg_cfg)
        if not self.cfg.allow_write:
            return {
                "ok": False,
                "skipped": True,
                "error": "write disabled",
                "preview": preview,
            }
        root = Path(self.cfg.staging_dir) / "_incoming"
        root.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        if "deb" in self.cfg.formats:
            ctrl = root / "control"
            ctrl.write_text(render_deb_control(pkg_cfg), encoding="utf-8")
            written.append(str(ctrl))
        if "rpm" in self.cfg.formats:
            spec = root / f"{self.cfg.package_name}.spec"
            spec.write_text(render_rpm_spec(pkg_cfg), encoding="utf-8")
            written.append(str(spec))
        return {"ok": True, "written": written, "preview": preview}

    def publish(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise DistroPublishError("distro publish disabled")
        staging = Path(self.cfg.staging_dir)
        if self.cfg.allow_write:
            self.stage_metadata()
        out = self.publisher.publish(formats=list(self.cfg.formats), staging=staging)
        if self.cfg.allow_remote and self.cfg.remote_url:
            # Soft remote: record intent only — never upload by default
            out["remote"] = {
                "attempted": False,
                "url": self.cfg.remote_url,
                "note": "remote mirror push requires explicit future contract wiring",
            }
        elif self.cfg.allow_remote and not self.cfg.remote_url:
            out["remote"] = {"attempted": False, "error": "remote_url empty"}
        with self._lock:
            self._publishes += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "formats": list(self.cfg.formats),
                "allow_write": self.cfg.allow_write,
                "allow_publish": self.cfg.allow_publish,
                "allow_remote": self.cfg.allow_remote,
                "reprepro": reprepro_available(),
                "createrepo": createrepo_available(),
                "publishes": self._publishes,
                "last": dict(self._last),
                "publisher": self.publisher.stats(),
            }


def build_distro_publisher(
    cfg: Optional[Mapping[str, Any] | DistroPublishConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[DistroPublisher]:
    if isinstance(cfg, DistroPublishConfig):
        resolved = cfg
    else:
        resolved = DistroPublishConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    backend = resolved.backend
    if backend == "reprepro":
        publisher: RepoPublisher = SoftRepreproPublisher(
            allow_publish=resolved.allow_publish
        )
    elif backend == "createrepo":
        publisher = SoftCreaterepoPublisher(allow_publish=resolved.allow_publish)
    elif backend == "auto":
        # Prefer matching tools; fall back to fake composite via Fake
        if "deb" in resolved.formats and reprepro_available():
            publisher = SoftRepreproPublisher(allow_publish=resolved.allow_publish)
        elif "rpm" in resolved.formats and createrepo_available():
            publisher = SoftCreaterepoPublisher(allow_publish=resolved.allow_publish)
        else:
            publisher = FakeRepoPublisher()
    else:
        publisher = FakeRepoPublisher()
    return DistroPublisher(cfg=resolved, publisher=publisher)
