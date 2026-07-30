"""
runtime/distro_packages.py
==========================
Linux distro packaging foundation (ADR-040).

Default-off. Renders .deb / .rpm control metadata under deploy/packaging/
and optionally writes stub package trees when allow_write. Does not
install packages as root by default (allow_install gated; Fake only in CI).
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from runtime.nats_supercluster import _truthy


class DistroPackageError(RuntimeError):
    """Distro packaging operation failed."""


@dataclass
class DistroPackageConfig:
    enabled: bool = False
    formats: list[str] = field(default_factory=lambda: ["deb", "rpm"])
    package_name: str = "kerros"
    version: str = "0.1.0"
    maintainer: str = "KerrOS <ops@kerros.local>"
    description: str = "KerrOS offline AI assistant and actor mesh"
    output_dir: str = "deploy/packaging"
    allow_write: bool = False
    allow_install: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "DistroPackageConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_DISTRO")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        formats_raw = data.get("formats") or ["deb", "rpm"]
        env_f = os.environ.get("KERROS_ACTOR_MESH_DISTRO_FORMATS")
        if env_f is not None:
            formats = [s.strip().lower() for s in env_f.replace(",", " ").split() if s.strip()]
        elif isinstance(formats_raw, str):
            formats = [s.strip().lower() for s in formats_raw.replace(",", " ").split() if s.strip()]
        else:
            formats = [str(s).strip().lower() for s in formats_raw if str(s).strip()]

        name = os.environ.get("KERROS_ACTOR_MESH_DISTRO_NAME")
        if name is None:
            name = str(data.get("package_name") or "kerros")

        version = os.environ.get("KERROS_ACTOR_MESH_DISTRO_VERSION")
        if version is None:
            version = str(data.get("version") or "0.1.0")

        maintainer = os.environ.get("KERROS_ACTOR_MESH_DISTRO_MAINTAINER")
        if maintainer is None:
            maintainer = str(data.get("maintainer") or "KerrOS <ops@kerros.local>")

        description = os.environ.get("KERROS_ACTOR_MESH_DISTRO_DESC")
        if description is None:
            description = str(
                data.get("description") or "KerrOS offline AI assistant and actor mesh"
            )

        out_dir = os.environ.get("KERROS_ACTOR_MESH_DISTRO_DIR")
        if out_dir is None:
            out_dir = str(data.get("output_dir") or "deploy/packaging")
        path = Path(out_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_DISTRO_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_install = data.get("allow_install", False)
        env_i = os.environ.get("KERROS_ACTOR_MESH_DISTRO_INSTALL")
        if env_i is not None:
            allow_install = _truthy(env_i)
        else:
            allow_install = _truthy(allow_install)

        return cls(
            enabled=bool(enabled),
            formats=formats or ["deb", "rpm"],
            package_name=str(name or "kerros").strip() or "kerros",
            version=str(version or "0.1.0").strip() or "0.1.0",
            maintainer=str(maintainer or "KerrOS <ops@kerros.local>").strip(),
            description=str(description or "").strip(),
            output_dir=str(path),
            allow_write=bool(allow_write),
            allow_install=bool(allow_install),
        )


def render_deb_control(cfg: DistroPackageConfig) -> str:
    return "\n".join(
        [
            f"Package: {cfg.package_name}",
            f"Version: {cfg.version}",
            "Section: utils",
            "Priority: optional",
            "Architecture: all",
            f"Maintainer: {cfg.maintainer}",
            f"Description: {cfg.description}",
            "Depends: python3 (>= 3.10)",
            "",
        ]
    )


def render_rpm_spec(cfg: DistroPackageConfig) -> str:
    return "\n".join(
        [
            f"Name:           {cfg.package_name}",
            f"Version:        {cfg.version}",
            "Release:        1%{?dist}",
            f"Summary:        {cfg.description}",
            "License:        Proprietary",
            "BuildArch:      noarch",
            "Requires:       python3 >= 3.10",
            "",
            "%description",
            cfg.description,
            "",
            "%files",
            "# populated by packaging CI — foundation stub",
            "",
            "%changelog",
            f"* Wed Jul 30 2026 {cfg.maintainer} - {cfg.version}-1",
            "- Initial foundation packaging stub (ADR-040)",
            "",
        ]
    )


@dataclass
class DistroPackager:
    """Render and optionally write .deb/.rpm packaging stubs."""

    cfg: DistroPackageConfig
    _writes: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def preview(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "package_name": self.cfg.package_name,
            "version": self.cfg.version,
            "formats": list(self.cfg.formats),
        }
        if "deb" in self.cfg.formats:
            out["deb_control"] = render_deb_control(self.cfg)
        if "rpm" in self.cfg.formats:
            out["rpm_spec"] = render_rpm_spec(self.cfg)
        return out

    def write_stubs(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise DistroPackageError("distro packaging disabled")
        preview = self.preview()
        if not self.cfg.allow_write:
            return {
                "ok": False,
                "skipped": True,
                "error": "write disabled",
                "preview": preview,
            }
        root = Path(self.cfg.output_dir)
        written: list[str] = []
        if "deb" in self.cfg.formats:
            deb_dir = root / "deb" / "DEBIAN"
            deb_dir.mkdir(parents=True, exist_ok=True)
            ctrl = deb_dir / "control"
            ctrl.write_text(render_deb_control(self.cfg), encoding="utf-8")
            written.append(str(ctrl))
            readme = root / "deb" / "README.stub"
            readme.write_text(
                "Foundation .deb tree — not a published package.\n",
                encoding="utf-8",
            )
            written.append(str(readme))
        if "rpm" in self.cfg.formats:
            rpm_dir = root / "rpm"
            rpm_dir.mkdir(parents=True, exist_ok=True)
            spec = rpm_dir / f"{self.cfg.package_name}.spec"
            spec.write_text(render_rpm_spec(self.cfg), encoding="utf-8")
            written.append(str(spec))
        out = {
            "ok": True,
            "written": written,
            "at": time.time(),
            "note": "metadata stubs only — not published to apt/yum",
        }
        with self._lock:
            self._writes += 1
            self._last = dict(out)
        return out

    def install_stub(self) -> dict[str, Any]:
        """Gated install simulation — never runs dpkg/rpm as root in CI."""
        if not self.cfg.enabled:
            raise DistroPackageError("distro packaging disabled")
        if not self.cfg.allow_install:
            return {
                "ok": False,
                "skipped": True,
                "error": "install disabled",
                "note": "set allow_install for staged install simulation only",
            }
        # Soft simulation: copy stub tree to a local staging dir under output
        stage = Path(self.cfg.output_dir) / "_install_stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "INSTALLED").write_text(
            f"{self.cfg.package_name}={self.cfg.version}\n",
            encoding="utf-8",
        )
        return {
            "ok": True,
            "staged": str(stage),
            "note": "local stage only — no system package manager invoked",
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "formats": list(self.cfg.formats),
                "package_name": self.cfg.package_name,
                "version": self.cfg.version,
                "allow_write": self.cfg.allow_write,
                "allow_install": self.cfg.allow_install,
                "writes": self._writes,
                "last": dict(self._last),
            }


def build_distro_packager(
    cfg: Optional[Mapping[str, Any] | DistroPackageConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[DistroPackager]:
    if isinstance(cfg, DistroPackageConfig):
        resolved = cfg
    else:
        resolved = DistroPackageConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return DistroPackager(cfg=resolved)
