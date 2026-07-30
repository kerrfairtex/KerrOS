"""
runtime/k8s_operator.py
=======================
Kubernetes *operator* facade foundation (ADR-038).

Default-off. Applies/deletes soft NATS fleet manifests via an in-memory
Fake cluster or soft ``kubectl apply -f`` when allow_live. Not a real
controller-runtime operator — a CI-safe apply/reconcile stub.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from runtime.nats_supercluster import _truthy


class K8sOperatorError(RuntimeError):
    """Kubernetes operator facade failed."""


@runtime_checkable
class K8sClusterBackend(Protocol):
    def apply(self, manifest: Mapping[str, Any]) -> dict[str, Any]: ...

    def delete(self, name: str, *, kind: str = "NatsBroker") -> dict[str, Any]: ...

    def list_resources(self, *, kind: str = "NatsBroker") -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeK8sCluster:
    """In-memory Kubernetes API stub."""

    _resources: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def apply(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        meta = dict(manifest.get("metadata") or {})
        name = str(meta.get("name") or "").strip()
        kind = str(manifest.get("kind") or "NatsBroker").strip() or "NatsBroker"
        if not name:
            raise K8sOperatorError("metadata.name required")
        key = f"{kind}/{name}"
        with self._lock:
            existing = self._resources.get(key)
            doc = {
                "apiVersion": str(manifest.get("apiVersion") or "kerros.io/v1"),
                "kind": kind,
                "metadata": meta,
                "spec": dict(manifest.get("spec") or {}),
                "status": {"phase": "Ready", "observed_at": time.time()},
            }
            self._resources[key] = doc
            created = existing is None
        return {"ok": True, "created": created, "key": key, "backend": "fake"}

    def delete(self, name: str, *, kind: str = "NatsBroker") -> dict[str, Any]:
        key = f"{kind}/{str(name).strip()}"
        with self._lock:
            existed = self._resources.pop(key, None) is not None
        return {"ok": True, "deleted": existed, "key": key, "backend": "fake"}

    def list_resources(self, *, kind: str = "NatsBroker") -> list[dict[str, Any]]:
        prefix = f"{kind}/"
        with self._lock:
            return [dict(v) for k, v in self._resources.items() if k.startswith(prefix)]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"backend": "fake", "resources": len(self._resources)}


@dataclass
class SoftKubectlBackend:
    """Soft kubectl apply/delete when allow_live; otherwise shadows Fake."""

    allow_live: bool = False
    kubectl_bin: str = "kubectl"
    namespace: str = "kerros"
    timeout_s: float = 30.0
    _shadow: FakeK8sCluster = field(default_factory=FakeK8sCluster)
    _last: dict[str, Any] = field(default_factory=dict)

    def apply(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.apply(manifest)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        path = shutil.which(self.kubectl_bin)
        if not path:
            return {"ok": False, "skipped": True, "error": f"{self.kubectl_bin} not on PATH"}
        import json

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(dict(manifest), fh)
            tmp = fh.name
        try:
            proc = subprocess.run(
                [path, "apply", "-f", tmp, "-n", self.namespace],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
            out = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-1000:],
                "stderr": (proc.stderr or "")[-1000:],
                "backend": "kubectl",
            }
            if out["ok"]:
                self._shadow.apply(manifest)
            self._last = dict(out)
            return out
        except Exception as exc:
            out = {"ok": False, "error": str(exc), "backend": "kubectl"}
            self._last = dict(out)
            return out
        finally:
            try:
                Path(tmp).unlink(missing_ok=True)
            except Exception:
                pass

    def delete(self, name: str, *, kind: str = "NatsBroker") -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.delete(name, kind=kind)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        path = shutil.which(self.kubectl_bin)
        if not path:
            return {"ok": False, "skipped": True, "error": f"{self.kubectl_bin} not on PATH"}
        try:
            proc = subprocess.run(
                [path, "delete", kind.lower(), name, "-n", self.namespace, "--ignore-not-found"],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
            out = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-1000:],
                "stderr": (proc.stderr or "")[-1000:],
                "backend": "kubectl",
            }
            if out["ok"]:
                self._shadow.delete(name, kind=kind)
            self._last = dict(out)
            return out
        except Exception as exc:
            out = {"ok": False, "error": str(exc)}
            self._last = dict(out)
            return out

    def list_resources(self, *, kind: str = "NatsBroker") -> list[dict[str, Any]]:
        return self._shadow.list_resources(kind=kind)

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "kubectl",
            "allow_live": self.allow_live,
            "namespace": self.namespace,
            "available": shutil.which(self.kubectl_bin) is not None,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


def nats_broker_manifest(
    name: str,
    *,
    replicas: int = 1,
    image: str = "nats:2",
    labels: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    return {
        "apiVersion": "kerros.io/v1",
        "kind": "NatsBroker",
        "metadata": {"name": name, "labels": dict(labels or {"app": "nats"})},
        "spec": {"replicas": int(replicas), "image": image},
    }


@dataclass
class K8sOperatorConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | kubectl
    allow_live: bool = False
    namespace: str = "kerros"
    kubectl_bin: str = "kubectl"

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "K8sOperatorConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_K8S_OPERATOR")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_K8S_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_K8S_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        ns = os.environ.get("KERROS_ACTOR_MESH_K8S_NAMESPACE")
        if ns is None:
            ns = str(data.get("namespace") or "kerros")

        kubectl = os.environ.get("KERROS_ACTOR_MESH_KUBECTL")
        if kubectl is None:
            kubectl = str(data.get("kubectl_bin") or "kubectl")

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            namespace=str(ns or "kerros").strip() or "kerros",
            kubectl_bin=str(kubectl or "kubectl").strip() or "kubectl",
        )


@dataclass
class K8sFleetOperator:
    """Reconcile desired NATS broker CRs against a cluster backend."""

    cfg: K8sOperatorConfig
    backend: K8sClusterBackend = field(default_factory=FakeK8sCluster)
    _desired: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def apply_broker(self, name: str, *, replicas: int = 1) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise K8sOperatorError("k8s operator disabled")
        manifest = nats_broker_manifest(name, replicas=replicas)
        out = self.backend.apply(manifest)
        with self._lock:
            if name not in self._desired:
                self._desired.append(name)
        return out

    def delete_broker(self, name: str) -> dict[str, Any]:
        out = self.backend.delete(name, kind="NatsBroker")
        with self._lock:
            if name in self._desired:
                self._desired.remove(name)
        return out

    def reconcile(self, desired: list[str]) -> dict[str, Any]:
        """Ensure desired broker names exist; delete extras from desired tracking."""
        results: list[dict[str, Any]] = []
        for name in desired:
            results.append(self.apply_broker(name))
        current = {r["metadata"]["name"] for r in self.backend.list_resources()}
        for name in list(current):
            if name not in desired:
                results.append(self.delete_broker(name))
        return {"ok": all(r.get("ok") for r in results) if results else True, "results": results}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "namespace": self.cfg.namespace,
                "desired": list(self._desired),
                "resources": len(self.backend.list_resources()),
                "cluster": self.backend.stats(),
            }


def build_k8s_fleet_operator(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    backend: K8sClusterBackend | None = None,
) -> K8sFleetOperator | None:
    kcfg = K8sOperatorConfig.from_mapping(cfg)
    if not kcfg.enabled:
        return None
    if backend is not None:
        be = backend
    elif kcfg.backend in ("kubectl", "k8s", "kubernetes"):
        be = SoftKubectlBackend(
            allow_live=kcfg.allow_live,
            kubectl_bin=kcfg.kubectl_bin,
            namespace=kcfg.namespace,
        )
    else:
        be = FakeK8sCluster()
    return K8sFleetOperator(cfg=kcfg, backend=be)
