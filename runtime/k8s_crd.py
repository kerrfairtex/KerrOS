"""
runtime/k8s_crd.py
==================
Kubernetes CRD / operator-sdk-style foundation (ADR-040).

Default-off. Renders/validates NatsBroker CustomResourceDefinition YAML
and applies soft CR instances via Fake or SoftKubectl backends. Not a
real operator-sdk project — CI-safe CRD packaging stubs.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from runtime.k8s_operator import (
    FakeK8sCluster,
    K8sClusterBackend,
    K8sOperatorError,
    SoftKubectlBackend,
)
from runtime.nats_supercluster import _truthy


def operator_sdk_available() -> bool:
    """Soft probe — operator-sdk is never a hard dependency."""
    try:
        import operator_sdk  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


NATS_BROKER_CRD: dict[str, Any] = {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "natsbrokers.kerros.io"},
    "spec": {
        "group": "kerros.io",
        "names": {
            "kind": "NatsBroker",
            "listKind": "NatsBrokerList",
            "plural": "natsbrokers",
            "singular": "natsbroker",
            "shortNames": ["nb"],
        },
        "scope": "Namespaced",
        "versions": [
            {
                "name": "v1",
                "served": True,
                "storage": True,
                "schema": {
                    "openAPIV3Schema": {
                        "type": "object",
                        "properties": {
                            "spec": {
                                "type": "object",
                                "properties": {
                                    "replicas": {"type": "integer"},
                                    "image": {"type": "string"},
                                    "clusterName": {"type": "string"},
                                    "jetstream": {"type": "boolean"},
                                },
                            },
                            "status": {
                                "type": "object",
                                "properties": {
                                    "phase": {"type": "string"},
                                    "observed_at": {"type": "number"},
                                },
                            },
                        },
                    }
                },
            }
        ],
    },
}


def render_nats_broker_crd() -> dict[str, Any]:
    """Return a deep copy of the NatsBroker CRD document."""
    import copy

    return copy.deepcopy(NATS_BROKER_CRD)


def validate_crd(doc: Mapping[str, Any]) -> list[str]:
    """Return validation error strings (empty = ok)."""
    errors: list[str] = []
    if str(doc.get("kind") or "") != "CustomResourceDefinition":
        errors.append("kind must be CustomResourceDefinition")
    if str(doc.get("apiVersion") or "") != "apiextensions.k8s.io/v1":
        errors.append("apiVersion must be apiextensions.k8s.io/v1")
    meta = dict(doc.get("metadata") or {})
    if not str(meta.get("name") or "").strip():
        errors.append("metadata.name required")
    spec = dict(doc.get("spec") or {})
    if not str(spec.get("group") or "").strip():
        errors.append("spec.group required")
    names = dict(spec.get("names") or {})
    if not str(names.get("kind") or "").strip():
        errors.append("spec.names.kind required")
    if not str(names.get("plural") or "").strip():
        errors.append("spec.names.plural required")
    versions = list(spec.get("versions") or [])
    if not versions:
        errors.append("spec.versions required")
    return errors


def render_cr(
    name: str,
    *,
    replicas: int = 1,
    image: str = "nats:2.10-alpine",
    cluster_name: str = "kerros",
    jetstream: bool = True,
    namespace: str = "kerros",
) -> dict[str, Any]:
    """Render a NatsBroker custom resource instance."""
    n = str(name or "").strip()
    if not n:
        raise K8sOperatorError("CR name required")
    return {
        "apiVersion": "kerros.io/v1",
        "kind": "NatsBroker",
        "metadata": {"name": n, "namespace": str(namespace or "kerros").strip() or "kerros"},
        "spec": {
            "replicas": max(1, int(replicas)),
            "image": str(image or "nats:2.10-alpine"),
            "clusterName": str(cluster_name or "kerros"),
            "jetstream": bool(jetstream),
        },
    }


@dataclass
class K8sCrdConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | kubectl
    allow_live: bool = False
    kubectl_bin: str = "kubectl"
    namespace: str = "kerros"
    crd_path: str = "deploy/k8s/crds/natsbroker.yaml"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "K8sCrdConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_K8S_CRD")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_K8S_CRD_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_K8S_CRD_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        kubectl = os.environ.get("KERROS_ACTOR_MESH_KUBECTL")
        if kubectl is None:
            kubectl = str(data.get("kubectl_bin") or "kubectl")

        ns = os.environ.get("KERROS_ACTOR_MESH_K8S_NS")
        if ns is None:
            ns = str(data.get("namespace") or "kerros")

        crd_path = os.environ.get("KERROS_ACTOR_MESH_K8S_CRD_PATH")
        if crd_path is None:
            crd_path = str(data.get("crd_path") or "deploy/k8s/crds/natsbroker.yaml")
        path = Path(crd_path)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            kubectl_bin=str(kubectl or "kubectl").strip() or "kubectl",
            namespace=str(ns or "kerros").strip() or "kerros",
            crd_path=str(path),
        )


@dataclass
class K8sCrdFacade:
    """Apply CRD + CR instances via Fake or soft kubectl."""

    cfg: K8sCrdConfig
    cluster: K8sClusterBackend = field(default_factory=FakeK8sCluster)
    _applies: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def crd_document(self) -> dict[str, Any]:
        return render_nats_broker_crd()

    def validate(self) -> dict[str, Any]:
        doc = self.crd_document()
        errors = validate_crd(doc)
        return {"ok": not errors, "errors": errors, "name": doc["metadata"]["name"]}

    def apply_crd(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise K8sOperatorError("K8s CRD facade disabled")
        doc = self.crd_document()
        errors = validate_crd(doc)
        if errors:
            raise K8sOperatorError("; ".join(errors))
        out = self.cluster.apply(doc)
        with self._lock:
            self._applies += 1
            self._last = dict(out)
        return out

    def apply_cr(
        self,
        name: str,
        *,
        replicas: int = 1,
        image: str = "nats:2.10-alpine",
        cluster_name: str = "kerros",
        jetstream: bool = True,
    ) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise K8sOperatorError("K8s CRD facade disabled")
        cr = render_cr(
            name,
            replicas=replicas,
            image=image,
            cluster_name=cluster_name,
            jetstream=jetstream,
            namespace=self.cfg.namespace,
        )
        out = self.cluster.apply(cr)
        with self._lock:
            self._applies += 1
            self._last = dict(out)
        return out

    def write_crd_yaml(self, path: Optional[Path] = None) -> Path:
        """Write CRD YAML to disk (always allowed for packaging stubs)."""
        target = Path(path) if path is not None else Path(self.cfg.crd_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        doc = self.crd_document()
        # Minimal YAML without PyYAML hard dep
        lines = [
            f"apiVersion: {doc['apiVersion']}",
            f"kind: {doc['kind']}",
            "metadata:",
            f"  name: {doc['metadata']['name']}",
            "spec:",
            f"  group: {doc['spec']['group']}",
            "  names:",
            f"    kind: {doc['spec']['names']['kind']}",
            f"    plural: {doc['spec']['names']['plural']}",
            f"    singular: {doc['spec']['names']['singular']}",
            f"  scope: {doc['spec']['scope']}",
            "  versions:",
            "  - name: v1",
            "    served: true",
            "    storage: true",
            "# Full OpenAPI schema in runtime/k8s_crd.NATS_BROKER_CRD",
            f"# generated_at: {time.time()}",
            "# note: foundation CRD stub — not a live operator-sdk project",
        ]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "namespace": self.cfg.namespace,
                "applies": self._applies,
                "last": dict(self._last),
                "operator_sdk": operator_sdk_available(),
                "cluster": self.cluster.stats(),
            }


def build_k8s_crd(
    cfg: Optional[Mapping[str, Any] | K8sCrdConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[K8sCrdFacade]:
    if isinstance(cfg, K8sCrdConfig):
        resolved = cfg
    else:
        resolved = K8sCrdConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    if resolved.backend == "kubectl":
        cluster: K8sClusterBackend = SoftKubectlBackend(
            allow_live=resolved.allow_live,
            kubectl_bin=resolved.kubectl_bin,
            namespace=resolved.namespace,
        )
    else:
        cluster = FakeK8sCluster()
    return K8sCrdFacade(cfg=resolved, cluster=cluster)
