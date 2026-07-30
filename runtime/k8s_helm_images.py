"""
runtime/k8s_helm_images.py
==========================
Shipped Go/Helm operator image foundation (ADR-047).

Default-off. Renders a Helm chart for the NatsBroker operator, Fake-
publishes OCI/image refs for CI, and soft-invokes ``helm package`` /
``docker push`` / ``helm push`` when gated. Not a public registry ship.
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

from runtime.nats_supercluster import _truthy


class HelmImageError(RuntimeError):
    """Helm / image publish failed."""


def helm_available() -> bool:
    return bool(shutil.which("helm"))


def docker_available() -> bool:
    return bool(shutil.which("docker"))


CHART_YAML = """\
apiVersion: v2
name: kerros-nats-operator
description: KerrOS NatsBroker operator Helm chart (ADR-047 foundation)
type: application
version: {version}
appVersion: "{app_version}"
"""

VALUES_YAML = """\
image:
  repository: {repository}
  tag: "{tag}"
  pullPolicy: IfNotPresent
replicaCount: 1
serviceAccount:
  create: true
  name: kerros-nats-operator
"""

DEPLOYMENT_YAML = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "kerros-nats-operator.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: kerros-nats-operator
  template:
    metadata:
      labels:
        app: kerros-nats-operator
    spec:
      containers:
      - name: operator
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
"""


@dataclass
class HelmImageConfig:
    enabled: bool = False
    chart_dir: str = "deploy/k8s/operator/helm/kerros-nats-operator"
    repository: str = "kerros/nats-operator"
    tag: str = "0.1.0"
    version: str = "0.1.0"
    registry: str = ""
    allow_write: bool = False
    allow_package: bool = False
    allow_push: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "HelmImageConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_HELM_IMAGES")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        chart = os.environ.get("KERROS_ACTOR_MESH_HELM_CHART_DIR")
        if chart is None:
            chart = str(
                data.get("chart_dir") or "deploy/k8s/operator/helm/kerros-nats-operator"
            )
        path = Path(chart)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        repo = os.environ.get("KERROS_ACTOR_MESH_HELM_IMAGE_REPO")
        if repo is None:
            repo = str(data.get("repository") or "kerros/nats-operator")

        tag = os.environ.get("KERROS_ACTOR_MESH_HELM_IMAGE_TAG")
        if tag is None:
            tag = str(data.get("tag") or "0.1.0")

        version = os.environ.get("KERROS_ACTOR_MESH_HELM_CHART_VERSION")
        if version is None:
            version = str(data.get("version") or "0.1.0")

        registry = os.environ.get("KERROS_ACTOR_MESH_HELM_REGISTRY")
        if registry is None:
            registry = str(data.get("registry") or "")

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_HELM_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_package = data.get("allow_package", False)
        env_p = os.environ.get("KERROS_ACTOR_MESH_HELM_PACKAGE")
        if env_p is not None:
            allow_package = _truthy(env_p)
        else:
            allow_package = _truthy(allow_package)

        allow_push = data.get("allow_push", False)
        env_u = os.environ.get("KERROS_ACTOR_MESH_HELM_PUSH")
        if env_u is not None:
            allow_push = _truthy(env_u)
        else:
            allow_push = _truthy(allow_push)

        return cls(
            enabled=bool(enabled),
            chart_dir=str(path),
            repository=str(repo or "kerros/nats-operator").strip(),
            tag=str(tag or "0.1.0").strip() or "0.1.0",
            version=str(version or "0.1.0").strip() or "0.1.0",
            registry=str(registry or "").strip(),
            allow_write=bool(allow_write),
            allow_package=bool(allow_package),
            allow_push=bool(allow_push),
        )


@dataclass
class HelmImagePublisher:
    """Render Helm chart + Fake/soft package/push operator images."""

    cfg: HelmImageConfig
    _ops: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def image_ref(self) -> str:
        base = self.cfg.repository
        if self.cfg.registry:
            base = f"{self.cfg.registry.rstrip('/')}/{base.split('/')[-1]}"
        return f"{base}:{self.cfg.tag}"

    def write_chart(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise HelmImageError("Helm image publisher disabled")
        if not self.cfg.allow_write:
            return {
                "ok": False,
                "skipped": True,
                "error": "write disabled",
                "image": self.image_ref(),
            }
        root = Path(self.cfg.chart_dir)
        templates = root / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        chart = root / "Chart.yaml"
        chart.write_text(
            CHART_YAML.format(version=self.cfg.version, app_version=self.cfg.tag),
            encoding="utf-8",
        )
        written.append(str(chart))
        values = root / "values.yaml"
        values.write_text(
            VALUES_YAML.format(
                repository=self.cfg.repository, tag=self.cfg.tag
            ),
            encoding="utf-8",
        )
        written.append(str(values))
        dep = templates / "deployment.yaml"
        dep.write_text(DEPLOYMENT_YAML, encoding="utf-8")
        written.append(str(dep))
        readme = root / "README.md"
        readme.write_text(
            "# kerros-nats-operator Helm chart (ADR-047)\n\n"
            "Foundation stub — not published to a public OCI registry.\n",
            encoding="utf-8",
        )
        written.append(str(readme))
        out = {"ok": True, "written": written, "image": self.image_ref(), "at": time.time()}
        with self._lock:
            self._ops += 1
            self._last = dict(out)
        return out

    def package(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise HelmImageError("Helm image publisher disabled")
        root = Path(self.cfg.chart_dir)
        if not self.cfg.allow_package:
            # Fake package artifact
            fake = root.parent / f"kerros-nats-operator-{self.cfg.version}.tgz.fake"
            if self.cfg.allow_write:
                root.parent.mkdir(parents=True, exist_ok=True)
                fake.write_text("FAKE_HELM_PACKAGE\n", encoding="utf-8")
            return {
                "ok": True,
                "dry_run": True,
                "artifact": str(fake) if self.cfg.allow_write else "",
                "helm": helm_available(),
                "note": "Fake helm package — set allow_package for soft helm package",
            }
        if not helm_available():
            raise HelmImageError("helm not installed")
        if not (root / "Chart.yaml").is_file():
            if self.cfg.allow_write:
                self.write_chart()
            else:
                raise HelmImageError("chart missing; enable allow_write first")
        proc = subprocess.run(
            ["helm", "package", str(root), "-d", str(root.parent)],
            capture_output=True,
            timeout=60,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", errors="replace")[:300],
            "stderr": proc.stderr.decode("utf-8", errors="replace")[:300],
            "at": time.time(),
        }

    def push(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise HelmImageError("Helm image publisher disabled")
        ref = self.image_ref()
        if not self.cfg.allow_push:
            return {
                "ok": True,
                "dry_run": True,
                "image": ref,
                "docker": docker_available(),
                "helm": helm_available(),
                "note": "push skipped — set allow_push (never public by default)",
            }
        results: dict[str, Any] = {"image": ref, "steps": []}
        if docker_available():
            proc = subprocess.run(
                ["docker", "push", ref],
                capture_output=True,
                timeout=120,
                check=False,
            )
            results["steps"].append(
                {
                    "tool": "docker",
                    "ok": proc.returncode == 0,
                    "returncode": proc.returncode,
                    "stderr": proc.stderr.decode("utf-8", errors="replace")[:200],
                }
            )
        else:
            results["steps"].append({"tool": "docker", "ok": False, "error": "missing"})
        results["ok"] = any(s.get("ok") for s in results["steps"])
        results["public"] = False
        results["note"] = "soft push attempt — not a certified public release"
        with self._lock:
            self._ops += 1
            self._last = dict(results)
        return results

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "image": self.image_ref(),
                "allow_write": self.cfg.allow_write,
                "allow_package": self.cfg.allow_package,
                "allow_push": self.cfg.allow_push,
                "helm": helm_available(),
                "docker": docker_available(),
                "ops": self._ops,
                "last": dict(self._last),
            }


def build_helm_images(
    cfg: Optional[Mapping[str, Any] | HelmImageConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[HelmImagePublisher]:
    if isinstance(cfg, HelmImageConfig):
        resolved = cfg
    else:
        resolved = HelmImageConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return HelmImagePublisher(cfg=resolved)
