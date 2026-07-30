"""
runtime/nats_supercluster.py
============================
NATS Supercluster / gateway / leafnode *topology registry* (ADR-030).

Default-off. Models clusters, gateway links, and leafnodes in-memory for
planning and health display. Does **not** start NATS servers — operators
still run the brokers; this is a config/validation foundation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class SuperclusterNode:
    name: str
    urls: list[str] = field(default_factory=list)
    role: str = "cluster"  # cluster | leaf | gateway
    region: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "urls": list(self.urls),
            "role": self.role,
            "region": self.region,
        }


@dataclass
class GatewayLink:
    from_cluster: str
    to_cluster: str
    gateway_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_cluster,
            "to": self.to_cluster,
            "gateway_url": self.gateway_url,
        }


@dataclass
class SuperclusterConfig:
    enabled: bool = False
    name: str = "kerros"
    clusters: list[dict[str, Any]] = field(default_factory=list)
    gateways: list[dict[str, Any]] = field(default_factory=list)
    leafnodes: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "SuperclusterConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        name = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_NAME")
        if name is None:
            name = str(data.get("name") or "kerros")

        return cls(
            enabled=bool(enabled),
            name=str(name or "kerros").strip() or "kerros",
            clusters=list(data.get("clusters") or []),
            gateways=list(data.get("gateways") or []),
            leafnodes=list(data.get("leafnodes") or []),
        )


class SuperclusterTopologyError(ValueError):
    """Topology validation failed."""


@dataclass
class SuperclusterTopology:
    """In-memory registry of Supercluster topology."""

    name: str = "kerros"
    _nodes: dict[str, SuperclusterNode] = field(default_factory=dict)
    _gateways: list[GatewayLink] = field(default_factory=list)
    _errors: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: SuperclusterConfig) -> "SuperclusterTopology":
        topo = cls(name=cfg.name)
        for raw in cfg.clusters:
            topo.add_node(
                SuperclusterNode(
                    name=str(raw.get("name") or "").strip(),
                    urls=[str(u).strip() for u in (raw.get("urls") or []) if str(u).strip()],
                    role="cluster",
                    region=str(raw.get("region") or ""),
                )
            )
        for raw in cfg.leafnodes:
            topo.add_node(
                SuperclusterNode(
                    name=str(raw.get("name") or "").strip(),
                    urls=[str(u).strip() for u in (raw.get("urls") or []) if str(u).strip()],
                    role="leaf",
                    region=str(raw.get("region") or ""),
                )
            )
        for raw in cfg.gateways:
            topo.add_gateway(
                GatewayLink(
                    from_cluster=str(raw.get("from") or raw.get("from_cluster") or "").strip(),
                    to_cluster=str(raw.get("to") or raw.get("to_cluster") or "").strip(),
                    gateway_url=str(raw.get("gateway_url") or raw.get("url") or "").strip(),
                )
            )
        return topo

    def add_node(self, node: SuperclusterNode) -> None:
        if not node.name:
            raise SuperclusterTopologyError("node name required")
        if node.name in self._nodes:
            raise SuperclusterTopologyError(f"duplicate node: {node.name}")
        role = str(node.role or "cluster").strip().lower()
        if role not in ("cluster", "leaf", "gateway"):
            raise SuperclusterTopologyError(f"invalid role: {node.role!r}")
        node.role = role
        self._nodes[node.name] = node

    def add_gateway(self, link: GatewayLink) -> None:
        if not link.from_cluster or not link.to_cluster:
            raise SuperclusterTopologyError("gateway requires from/to clusters")
        self._gateways.append(link)

    def validate(self) -> list[str]:
        """Return validation errors (empty = ok)."""
        errors: list[str] = []
        clusters = {
            n for n, node in self._nodes.items() if node.role == "cluster"
        }
        if not clusters and self._nodes:
            errors.append("no cluster-role nodes defined")
        for name, node in self._nodes.items():
            if node.role in ("cluster", "leaf") and not node.urls:
                errors.append(f"node {name!r} has no urls")
        for gw in self._gateways:
            if gw.from_cluster not in self._nodes:
                errors.append(f"gateway from unknown node {gw.from_cluster!r}")
            if gw.to_cluster not in self._nodes:
                errors.append(f"gateway to unknown node {gw.to_cluster!r}")
            if (
                gw.from_cluster in self._nodes
                and self._nodes[gw.from_cluster].role != "cluster"
            ):
                errors.append(
                    f"gateway from {gw.from_cluster!r} must be role=cluster"
                )
            if (
                gw.to_cluster in self._nodes
                and self._nodes[gw.to_cluster].role != "cluster"
            ):
                errors.append(
                    f"gateway to {gw.to_cluster!r} must be role=cluster"
                )
        # Leafnodes should reference a hub via optional hub field in urls[0] region — soft check only.
        self._errors = list(errors)
        return list(errors)

    def is_valid(self) -> bool:
        return not self.validate()

    def cluster_urls(self, name: str) -> list[str]:
        node = self._nodes.get(name)
        return list(node.urls) if node else []

    def all_urls(self) -> list[str]:
        out: list[str] = []
        for node in self._nodes.values():
            out.extend(node.urls)
        return out

    def stats(self) -> dict[str, Any]:
        by_role: dict[str, int] = {}
        for node in self._nodes.values():
            by_role[node.role] = by_role.get(node.role, 0) + 1
        return {
            "name": self.name,
            "nodes": len(self._nodes),
            "gateways": len(self._gateways),
            "by_role": by_role,
            "valid": self.is_valid(),
            "errors": list(self._errors) if self._errors else self.validate(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "gateways": [g.to_dict() for g in self._gateways],
            "stats": self.stats(),
        }


def build_supercluster_topology(
    cfg: Optional[Mapping[str, Any]] = None,
) -> SuperclusterTopology | None:
    sc = SuperclusterConfig.from_mapping(cfg)
    if not sc.enabled:
        return None
    return SuperclusterTopology.from_config(sc)
