"""
runtime/nats_supercluster_ops.py
================================
Supercluster topology *ops* foundation (ADR-031).

Default-off. Plans gateway/leaf attach actions, soft TCP probes of
declared URLs, and renders operator-facing NATS config snippets.
Does **not** start or reconfigure live NATS brokers — apply() only
records an in-memory ops ledger.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

from runtime.nats_supercluster import (
    SuperclusterConfig,
    SuperclusterTopology,
    _truthy,
)


class SuperclusterOpsError(RuntimeError):
    """Topology ops failed."""


ProbeFn = Callable[[str, float], dict[str, Any]]


def parse_host_port(url: str) -> tuple[str, int] | None:
    """Extract host/port from nats:// or host:port URLs. None if unparseable."""
    raw = str(url or "").strip()
    if not raw or raw.startswith("mem://"):
        return None
    if "://" not in raw:
        raw = "nats://" + raw
    parsed = urlparse(raw)
    host = parsed.hostname
    if not host:
        return None
    port = parsed.port or 4222
    return host, int(port)


def tcp_probe(url: str, timeout_s: float = 1.0) -> dict[str, Any]:
    """Soft TCP connect probe. Never raises."""
    parsed = parse_host_port(url)
    if parsed is None:
        return {
            "url": url,
            "ok": False,
            "skipped": True,
            "error": "unparseable or mem URL",
        }
    host, port = parsed
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=max(0.05, float(timeout_s))):
            pass
        return {
            "url": url,
            "ok": True,
            "host": host,
            "port": port,
            "latency_ms": round((time.monotonic() - started) * 1000.0, 2),
        }
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "host": host,
            "port": port,
            "error": str(exc),
            "latency_ms": round((time.monotonic() - started) * 1000.0, 2),
        }


@dataclass
class SuperclusterOpsConfig:
    enabled: bool = False
    probe_timeout_s: float = 1.0
    allow_probe: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "SuperclusterOpsConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_OPS")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        timeout = data.get("probe_timeout_s", 1.0)
        env_t = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_PROBE_TIMEOUT")
        if env_t is not None:
            timeout = float(env_t)

        probe = data.get("allow_probe", False)
        env_p = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_ALLOW_PROBE")
        if env_p is not None:
            probe = _truthy(env_p)
        else:
            probe = _truthy(probe)

        return cls(
            enabled=bool(enabled),
            probe_timeout_s=max(0.05, float(timeout or 1.0)),
            allow_probe=bool(probe),
        )


@dataclass
class SuperclusterOps:
    """Plan / probe / apply ledger over a SuperclusterTopology."""

    cfg: SuperclusterOpsConfig
    topology: SuperclusterTopology
    probe_fn: ProbeFn = field(default=tcp_probe)
    _plan: list[dict[str, Any]] = field(default_factory=list)
    _applied: list[dict[str, Any]] = field(default_factory=list)
    _last_probes: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def plan(self) -> list[dict[str, Any]]:
        """Build intended gateway + leaf attach actions from topology."""
        errors = self.topology.validate()
        actions: list[dict[str, Any]] = []
        for gw in self.topology._gateways:  # noqa: SLF001 — ops is same package family
            actions.append(
                {
                    "op": "gateway_link",
                    "from": gw.from_cluster,
                    "to": gw.to_cluster,
                    "gateway_url": gw.gateway_url,
                    "status": "planned",
                }
            )
        for name, node in self.topology._nodes.items():  # noqa: SLF001
            if node.role == "leaf":
                actions.append(
                    {
                        "op": "leafnode_attach",
                        "name": name,
                        "urls": list(node.urls),
                        "region": node.region,
                        "status": "planned",
                    }
                )
        with self._lock:
            self._plan = list(actions)
        return list(actions) if not errors else list(actions)

    def apply_plan(self) -> list[dict[str, Any]]:
        """
        Record planned actions as applied in-memory.
        Does not dial brokers or mutate remote config.
        """
        with self._lock:
            if not self._plan:
                self.plan()
            applied = []
            for action in self._plan:
                item = dict(action)
                item["status"] = "applied"
                item["applied_at"] = time.time()
                applied.append(item)
            self._applied = applied
            return list(applied)

    def probe_all(self) -> list[dict[str, Any]]:
        """TCP-probe all topology URLs when allow_probe is set."""
        if not self.cfg.allow_probe:
            return [{"ok": False, "skipped": True, "error": "probe disabled"}]
        results: list[dict[str, Any]] = []
        for url in self.topology.all_urls():
            results.append(self.probe_fn(url, self.cfg.probe_timeout_s))
        with self._lock:
            self._last_probes = list(results)
        return list(results)

    def render_nats_snippets(self) -> dict[str, str]:
        """Operator-facing NATS config fragments (not written to disk)."""
        gateways: list[str] = []
        for gw in self.topology._gateways:  # noqa: SLF001
            name = f"{gw.from_cluster}-{gw.to_cluster}"
            url = gw.gateway_url or "nats://gateway:7222"
            gateways.append(f"gateway {{\n  name: {name}\n  urls: [\"{url}\"]\n}}")
        leafs: list[str] = []
        for name, node in self.topology._nodes.items():  # noqa: SLF001
            if node.role != "leaf":
                continue
            urls = ", ".join(f'"{u}"' for u in node.urls) or '""'
            leafs.append(f"leafnodes {{\n  remotes: [{{urls: [{urls}]}}]  # {name}\n}}")
        return {
            "gateways": "\n\n".join(gateways),
            "leafnodes": "\n\n".join(leafs),
            "name": self.topology.name,
        }

    def health(self) -> dict[str, Any]:
        errors = self.topology.validate()
        probes = list(self._last_probes)
        probe_ok = all(p.get("ok") for p in probes) if probes else None
        return {
            "topology_valid": not errors,
            "errors": errors,
            "planned": len(self._plan),
            "applied": len(self._applied),
            "probes": probes,
            "probe_ok": probe_ok,
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "allow_probe": self.cfg.allow_probe,
                "probe_timeout_s": self.cfg.probe_timeout_s,
                "planned": len(self._plan),
                "applied": len(self._applied),
                "last_probes": len(self._last_probes),
                "topology": self.topology.stats(),
                "health": self.health(),
            }


def build_supercluster_ops(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    topology: SuperclusterTopology | None = None,
    probe_fn: ProbeFn | None = None,
) -> SuperclusterOps | None:
    data = dict(cfg or {})
    ops_cfg = SuperclusterOpsConfig.from_mapping(data.get("ops") or {})
    if not ops_cfg.enabled:
        return None
    topo = topology
    if topo is None:
        # Ops implies a topology object even if parent enabled flag is off.
        sc = SuperclusterConfig.from_mapping({**data, "enabled": True})
        topo = SuperclusterTopology.from_config(sc)
    return SuperclusterOps(
        cfg=ops_cfg,
        topology=topo,
        probe_fn=probe_fn or tcp_probe,
    )
