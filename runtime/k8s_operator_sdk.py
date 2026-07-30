"""
runtime/k8s_operator_sdk.py
===========================
Live operator-sdk / controller-runtime foundation (ADR-042).

Default-off. Emulates a controller-runtime reconcile loop with Fake
leader election + watch queue for CI, and soft kubectl when allow_live.
Optionally writes an operator project skeleton under deploy/k8s/operator/.
Not a real Go operator-sdk binary — Python CI-safe stubs.
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
from typing import Any, Mapping, Optional

from runtime.k8s_crd import render_cr, render_nats_broker_crd, validate_crd
from runtime.k8s_operator import FakeK8sCluster, K8sClusterBackend, SoftKubectlBackend
from runtime.nats_supercluster import _truthy


class OperatorSdkError(RuntimeError):
    """Operator-sdk controller facade failed."""


def operator_sdk_cli_available() -> bool:
    return bool(shutil.which("operator-sdk"))


def kubernetes_available() -> bool:
    try:
        import kubernetes  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class FakeLeaderElection:
    """In-memory leader election stub (always becomes leader)."""

    identity: str = "kerros-controller-0"
    _is_leader: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self) -> bool:
        with self._lock:
            self._is_leader = True
            return True

    def release(self) -> None:
        with self._lock:
            self._is_leader = False

    def is_leader(self) -> bool:
        with self._lock:
            return self._is_leader

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"backend": "fake", "identity": self.identity, "leader": self._is_leader}


@dataclass
class FakeWatchQueue:
    """Controller watch/event queue."""

    _events: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def enqueue(self, event_type: str, name: str, *, kind: str = "NatsBroker") -> None:
        with self._lock:
            self._events.append(
                {
                    "type": str(event_type).upper(),
                    "kind": kind,
                    "name": str(name).strip(),
                    "at": time.time(),
                }
            )

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
            return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"backend": "fake", "pending": len(self._events)}


@dataclass
class OperatorSdkConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | kubectl
    allow_live: bool = False
    allow_write: bool = False
    namespace: str = "kerros"
    kubectl_bin: str = "kubectl"
    project_dir: str = "deploy/k8s/operator"
    reconcile_interval_s: float = 5.0
    leader_identity: str = "kerros-controller-0"
    autostart: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "OperatorSdkConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_OPERATOR_SDK")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_OPERATOR_SDK_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_OPERATOR_SDK_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_OPERATOR_SDK_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        ns = os.environ.get("KERROS_ACTOR_MESH_K8S_NS")
        if ns is None:
            ns = str(data.get("namespace") or "kerros")

        kubectl = os.environ.get("KERROS_ACTOR_MESH_KUBECTL")
        if kubectl is None:
            kubectl = str(data.get("kubectl_bin") or "kubectl")

        project = os.environ.get("KERROS_ACTOR_MESH_OPERATOR_SDK_DIR")
        if project is None:
            project = str(data.get("project_dir") or "deploy/k8s/operator")
        path = Path(project)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        interval = data.get("reconcile_interval_s", 5.0)
        env_i = os.environ.get("KERROS_ACTOR_MESH_OPERATOR_SDK_INTERVAL")
        if env_i is not None:
            try:
                interval = float(env_i)
            except ValueError:
                pass

        identity = os.environ.get("KERROS_ACTOR_MESH_OPERATOR_SDK_IDENTITY")
        if identity is None:
            identity = str(data.get("leader_identity") or "kerros-controller-0")

        autostart = data.get("autostart", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_OPERATOR_SDK_AUTOSTART")
        if env_a is not None:
            autostart = _truthy(env_a)
        else:
            autostart = _truthy(autostart)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            allow_write=bool(allow_write),
            namespace=str(ns or "kerros").strip() or "kerros",
            kubectl_bin=str(kubectl or "kubectl").strip() or "kubectl",
            project_dir=str(path),
            reconcile_interval_s=max(0.1, float(interval or 5.0)),
            leader_identity=str(identity or "kerros-controller-0").strip(),
            autostart=bool(autostart),
        )


@dataclass
class OperatorSdkController:
    """Controller-runtime-style reconcile loop over NatsBroker CRs."""

    cfg: OperatorSdkConfig
    cluster: K8sClusterBackend = field(default_factory=FakeK8sCluster)
    leader: FakeLeaderElection = field(default_factory=FakeLeaderElection)
    queue: FakeWatchQueue = field(default_factory=FakeWatchQueue)
    _desired: list[str] = field(default_factory=list)
    _reconciles: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def set_desired(self, names: list[str]) -> None:
        with self._lock:
            self._desired = [str(n).strip() for n in names if str(n).strip()]
            for n in self._desired:
                self.queue.enqueue("ADDED", n)

    def ensure_crd(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise OperatorSdkError("operator-sdk controller disabled")
        doc = render_nats_broker_crd()
        errors = validate_crd(doc)
        if errors:
            raise OperatorSdkError("; ".join(errors))
        return self.cluster.apply(doc)

    def reconcile_once(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise OperatorSdkError("operator-sdk controller disabled")
        if not self.leader.is_leader():
            self.leader.acquire()
        if not self.leader.is_leader():
            return {"ok": False, "skipped": True, "error": "not leader"}

        events = self.queue.drain()
        with self._lock:
            desired = list(self._desired)

        # Apply desired CRs
        applied: list[str] = []
        for name in desired:
            cr = render_cr(name, namespace=self.cfg.namespace)
            self.cluster.apply(cr)
            applied.append(name)

        # Delete extras still in cluster
        existing = self.cluster.list_resources(kind="NatsBroker")
        deleted: list[str] = []
        desired_set = set(desired)
        for doc in existing:
            name = str((doc.get("metadata") or {}).get("name") or "")
            if name and name not in desired_set:
                self.cluster.delete(name, kind="NatsBroker")
                deleted.append(name)

        out = {
            "ok": True,
            "applied": applied,
            "deleted": deleted,
            "events": len(events),
            "leader": self.leader.identity,
            "at": time.time(),
            "note": "foundation controller — not a live operator-sdk Go binary",
        }
        with self._lock:
            self._reconciles += 1
            self._last = dict(out)
        return out

    def write_project_skeleton(self, path: Optional[Path] = None) -> dict[str, Any]:
        """Write a minimal operator project stub (gated by allow_write)."""
        if not self.cfg.enabled:
            raise OperatorSdkError("operator-sdk controller disabled")
        if not self.cfg.allow_write:
            return {
                "ok": False,
                "skipped": True,
                "error": "write disabled",
                "cli": operator_sdk_cli_available(),
                "kubernetes": kubernetes_available(),
            }
        root = Path(path) if path is not None else Path(self.cfg.project_dir)
        root.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        readme = root / "README.md"
        readme.write_text(
            "# KerrOS NatsBroker operator skeleton (ADR-042)\n\n"
            "Foundation stub — not generated by `operator-sdk init`.\n"
            "Enable live kubectl apply via `allow_live` when funded.\n",
            encoding="utf-8",
        )
        written.append(str(readme))
        main_py = root / "main.py"
        main_py.write_text(
            '"""Stub entrypoint — wire runtime.k8s_operator_sdk in production."""\n'
            "from runtime.k8s_operator_sdk import build_operator_sdk_controller\n\n"
            "def main() -> None:\n"
            '    ctl = build_operator_sdk_controller({"enabled": True})\n'
            "    if ctl is None:\n"
            "        return\n"
            "    ctl.ensure_crd()\n"
            "    ctl.reconcile_once()\n\n"
            'if __name__ == "__main__":\n'
            "    main()\n",
            encoding="utf-8",
        )
        written.append(str(main_py))
        watches = root / "watches.yaml"
        watches.write_text(
            "# Soft watches stub (operator-sdk ansible/helm style)\n"
            "- group: kerros.io\n"
            "  version: v1\n"
            "  kind: NatsBroker\n"
            "  reconcilePeriod: 5s\n",
            encoding="utf-8",
        )
        written.append(str(watches))
        return {"ok": True, "written": written, "at": time.time()}

    def soft_operator_sdk_init(self) -> dict[str, Any]:
        """Soft `operator-sdk init` probe — never runs unless allow_live."""
        if not self.cfg.enabled:
            raise OperatorSdkError("operator-sdk controller disabled")
        if not self.cfg.allow_live:
            return {
                "ok": True,
                "dry_run": True,
                "cli": operator_sdk_cli_available(),
                "note": "skipped live operator-sdk init",
            }
        if not operator_sdk_cli_available():
            raise OperatorSdkError("operator-sdk CLI not installed")
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [
                    "operator-sdk",
                    "init",
                    "--domain",
                    "kerros.io",
                    "--repo",
                    "github.com/kerros/nats-operator",
                ],
                cwd=td,
                capture_output=True,
                timeout=60,
                check=False,
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout.decode("utf-8", errors="replace")[:500],
                "stderr": proc.stderr.decode("utf-8", errors="replace")[:500],
            }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.leader.acquire()
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(self.cfg.reconcile_interval_s):
                try:
                    self.reconcile_once()
                except Exception:
                    pass

        self._thread = threading.Thread(
            target=_loop, name="kerros-operator-sdk", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self.leader.release()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "allow_write": self.cfg.allow_write,
                "namespace": self.cfg.namespace,
                "reconciles": self._reconciles,
                "desired": list(self._desired),
                "last": dict(self._last),
                "leader": self.leader.stats(),
                "queue": self.queue.stats(),
                "operator_sdk_cli": operator_sdk_cli_available(),
                "kubernetes": kubernetes_available(),
                "cluster": self.cluster.stats(),
                "running": bool(self._thread and self._thread.is_alive()),
            }


def build_operator_sdk_controller(
    cfg: Optional[Mapping[str, Any] | OperatorSdkConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[OperatorSdkController]:
    raw: Mapping[str, Any] = cfg if isinstance(cfg, Mapping) else {}
    if isinstance(cfg, OperatorSdkConfig):
        resolved = cfg
    else:
        resolved = OperatorSdkConfig.from_mapping(cfg, base=base)
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
    ctl = OperatorSdkController(
        cfg=resolved,
        cluster=cluster,
        leader=FakeLeaderElection(identity=resolved.leader_identity),
    )
    desired = list(raw.get("desired") or [])
    if desired:
        ctl.set_desired([str(x) for x in desired])
    if resolved.autostart:
        try:
            ctl.ensure_crd()
            ctl.start()
        except Exception:
            pass
    return ctl
