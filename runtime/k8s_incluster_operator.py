"""
runtime/k8s_incluster_operator.py
=================================
In-cluster Kubernetes operator foundation (ADR-039).

Default-off. Runs a reconcile loop against an injectable informer /
cluster backend. Detects in-cluster service-account paths softly.
CI uses ``FakeInformer`` — no kubeconfig or API server required.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

from runtime.k8s_operator import (
    FakeK8sCluster,
    K8sClusterBackend,
    K8sFleetOperator,
    K8sOperatorConfig,
)
from runtime.nats_supercluster import _truthy


class InClusterOperatorError(RuntimeError):
    """In-cluster operator failed."""


def detect_in_cluster(
    *,
    token_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/token",
    ca_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
    host_env: str = "KUBERNETES_SERVICE_HOST",
) -> dict[str, Any]:
    """Soft detection of in-cluster credentials (never raises)."""
    token = Path(token_path)
    ca = Path(ca_path)
    host = os.environ.get(host_env, "")
    present = token.is_file() and ca.is_file() and bool(host)
    return {
        "in_cluster": present,
        "token_present": token.is_file(),
        "ca_present": ca.is_file(),
        "api_host": host,
    }


@runtime_checkable
class Informer(Protocol):
    def list_desired(self) -> list[str]: ...

    def watch_once(self) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeInformer:
    """CI-safe desired-state informer."""

    desired: list[str] = field(default_factory=list)
    _events: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set_desired(self, names: list[str]) -> None:
        with self._lock:
            self.desired = [str(n).strip() for n in names if str(n).strip()]
            self._events.append(
                {"type": "SYNC", "desired": list(self.desired), "at": time.time()}
            )

    def list_desired(self) -> list[str]:
        with self._lock:
            return list(self.desired)

    def watch_once(self) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"backend": "fake", "desired": len(self.desired), "pending_events": len(self._events)}


ReconcileHook = Callable[[list[str]], dict[str, Any]]


@dataclass
class InClusterOperatorConfig:
    enabled: bool = False
    reconcile_interval_s: float = 5.0
    autostart: bool = False
    require_in_cluster: bool = False
    namespace: str = "kerros"

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "InClusterOperatorConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_K8S_INCLUSTER")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        interval = data.get("reconcile_interval_s", 5.0)
        env_i = os.environ.get("KERROS_ACTOR_MESH_K8S_INCLUSTER_INTERVAL")
        if env_i is not None:
            interval = float(env_i)

        autostart = data.get("autostart", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_K8S_INCLUSTER_AUTOSTART")
        if env_a is not None:
            autostart = _truthy(env_a)
        else:
            autostart = _truthy(autostart)

        require = data.get("require_in_cluster", False)
        env_r = os.environ.get("KERROS_ACTOR_MESH_K8S_INCLUSTER_REQUIRE")
        if env_r is not None:
            require = _truthy(env_r)
        else:
            require = _truthy(require)

        ns = os.environ.get("KERROS_ACTOR_MESH_K8S_NAMESPACE")
        if ns is None:
            ns = str(data.get("namespace") or "kerros")

        return cls(
            enabled=bool(enabled),
            reconcile_interval_s=max(0.1, float(interval or 5.0)),
            autostart=bool(autostart),
            require_in_cluster=bool(require),
            namespace=str(ns or "kerros").strip() or "kerros",
        )


@dataclass
class InClusterNatsOperator:
    """
    Watch/reconcile loop for NatsBroker desired names.
    Uses FakeInformer in CI; optionally requires in-cluster SA.
    """

    cfg: InClusterOperatorConfig
    informer: Informer = field(default_factory=FakeInformer)
    fleet_operator: K8sFleetOperator | None = None
    cluster: K8sClusterBackend = field(default_factory=FakeK8sCluster)
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _reconciles: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _detection: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._detection = detect_in_cluster()
        if self.fleet_operator is None:
            self.fleet_operator = K8sFleetOperator(
                cfg=K8sOperatorConfig(
                    enabled=True, backend="fake", namespace=self.cfg.namespace
                ),
                backend=self.cluster,
            )

    def reconcile_once(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise InClusterOperatorError("in-cluster operator disabled")
        if self.cfg.require_in_cluster and not self._detection.get("in_cluster"):
            out = {
                "ok": False,
                "skipped": True,
                "error": "not running in-cluster",
                "detection": dict(self._detection),
            }
            with self._lock:
                self._last = dict(out)
            return out
        events = self.informer.watch_once()
        desired = self.informer.list_desired()
        assert self.fleet_operator is not None
        result = self.fleet_operator.reconcile(desired)
        out = {
            "ok": bool(result.get("ok")),
            "desired": desired,
            "events": events,
            "result": result,
            "at": time.time(),
            "detection": dict(self._detection),
        }
        with self._lock:
            self._reconciles += 1
            self._last = dict(out)
        return out

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(self.cfg.reconcile_interval_s):
                try:
                    self.reconcile_once()
                except Exception as exc:
                    with self._lock:
                        self._last = {"ok": False, "error": str(exc)}

        self._thread = threading.Thread(
            target=_loop, name="k8s-incluster-operator", daemon=True
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
                "running": self._thread is not None,
                "reconciles": self._reconciles,
                "interval_s": self.cfg.reconcile_interval_s,
                "require_in_cluster": self.cfg.require_in_cluster,
                "detection": dict(self._detection),
                "informer": self.informer.stats(),
                "last": dict(self._last),
                "fleet": self.fleet_operator.stats() if self.fleet_operator else {},
            }


def build_incluster_nats_operator(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    informer: Informer | None = None,
    cluster: K8sClusterBackend | None = None,
) -> InClusterNatsOperator | None:
    icfg = InClusterOperatorConfig.from_mapping(cfg)
    if not icfg.enabled:
        return None
    op = InClusterNatsOperator(
        cfg=icfg,
        informer=informer or FakeInformer(),
        cluster=cluster or FakeK8sCluster(),
    )
    # Seed empty desired unless informer already set.
    if isinstance(op.informer, FakeInformer) and not op.informer.list_desired():
        desired = cfg.get("desired") if isinstance(cfg, Mapping) else None
        if desired:
            op.informer.set_desired([str(x) for x in desired])
    if icfg.autostart:
        op.start()
    return op
