"""
adapters/llm/vllm_multinode.py
================================
Multi-node vLLM topology foundation (C-19 / ADR-049).

Default-off. Fake-plans tensor-parallel / Ray-style node envelopes.
Soft dry-run only when ``allow_live`` — ``cluster_ready`` stays False
without real node confirm. Not a production HA / NCCL seal.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class VllmMultinodeError(RuntimeError):
    """Multi-node vLLM planning failed."""


@dataclass
class VllmMultinodeConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | ray | compose
    model: str = "meta-llama/Llama-3.2-3B-Instruct"
    tensor_parallel: int = 2
    nodes: list[str] = field(default_factory=lambda: ["vllm-node-a", "vllm-node-b"])
    allow_live: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "VllmMultinodeConfig":
        _ = base
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_VLLM_MULTINODE")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_VLLM_MULTINODE_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        model = os.environ.get("KERROS_VLLM_MULTINODE_MODEL") or os.environ.get(
            "VLLM_MODEL"
        )
        if model is None:
            model = str(data.get("model") or "meta-llama/Llama-3.2-3B-Instruct")

        tp = data.get("tensor_parallel", 2)
        env_tp = os.environ.get("KERROS_VLLM_MULTINODE_TP")
        if env_tp is not None:
            try:
                tp = int(env_tp)
            except ValueError:
                tp = 2
        else:
            try:
                tp = int(tp)
            except (TypeError, ValueError):
                tp = 2

        nodes_raw = data.get("nodes")
        env_nodes = os.environ.get("KERROS_VLLM_MULTINODE_NODES")
        if env_nodes is not None:
            nodes = [n.strip() for n in env_nodes.split(",") if n.strip()]
        elif isinstance(nodes_raw, Sequence) and not isinstance(nodes_raw, (str, bytes)):
            nodes = [str(n).strip() for n in nodes_raw if str(n).strip()]
        else:
            nodes = ["vllm-node-a", "vllm-node-b"]

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_VLLM_MULTINODE_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            model=str(model or "").strip(),
            tensor_parallel=max(1, int(tp)),
            nodes=list(nodes) or ["vllm-node-a", "vllm-node-b"],
            allow_live=bool(allow_live),
        )


@dataclass
class VllmMultinodePlanner:
    """Plan a multi-node vLLM topology envelope."""

    cfg: VllmMultinodeConfig
    _plans: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def plan(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise VllmMultinodeError("vLLM multinode disabled")
        out: dict[str, Any] = {
            "ok": True,
            "backend": self.cfg.backend,
            "model": self.cfg.model,
            "tensor_parallel": self.cfg.tensor_parallel,
            "nodes": list(self.cfg.nodes),
            "node_count": len(self.cfg.nodes),
            "cluster_ready": False,
            "dry_run": True,
            "note": "Fake multi-node plan — not Ray/NCCL production HA",
            "at": time.time(),
        }
        if self.cfg.allow_live:
            out["dry_run"] = False
            out["cluster_ready"] = False  # never silent without live nodes
            out["note"] = (
                "Soft live gate on — cluster_ready stays False without "
                "contract-funded GPU nodes"
            )
        with self._lock:
            self._plans += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "model": self.cfg.model,
                "tensor_parallel": self.cfg.tensor_parallel,
                "nodes": list(self.cfg.nodes),
                "allow_live": self.cfg.allow_live,
                "plans": self._plans,
                "last": dict(self._last),
            }


def build_vllm_multinode(
    cfg: Optional[Mapping[str, Any] | VllmMultinodeConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[VllmMultinodePlanner]:
    if isinstance(cfg, VllmMultinodeConfig):
        resolved = cfg
    else:
        resolved = VllmMultinodeConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return VllmMultinodePlanner(cfg=resolved)
