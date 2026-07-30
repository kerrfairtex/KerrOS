"""
kernel/boot.py
==============
Kernel boot lifecycle — config load, service registration, port wiring.

Boot order (deterministic):
  INIT → CONFIG → SERVICES → PORTS → READY

Shutdown clears the container and returns to INIT.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kernel.config import KernelConfig, load_config
from kernel.container import Container
from kernel.contract import (
    BootPhase,
    KernelBootError,
    KernelNotReadyError,
    SERVICE_CONFIG,
    SERVICE_DECISION_LOG,
    SERVICE_DISPATCH_PORT,
    SERVICE_EVENT_BUS,
    SERVICE_EVENT_MESH,
    SERVICE_SERVICE_BUS,
    SERVICE_ACTOR_MESH,
    SERVICE_HEALTH_MONITOR,
    SERVICE_LLM_PORT,
    SERVICE_SCHEDULER,
    SERVICE_WORKFLOW_ENGINE,
    SERVICE_MEMORY_PORT,
    SERVICE_ROUTER,
    SERVICE_SERVICE_MANAGER,
    SERVICE_TOOL_PORT,
    SERVICE_STORAGE_PORT,
    SERVICE_DATABASE_PORT,
    SERVICE_EMBEDDING_PORT,
    SERVICE_SEARCH_PORT,
    SERVICE_CAPABILITY_REGISTRY,
)


@dataclass
class Kernel:
    """Kernel runtime — owns lifecycle phase and DI container."""

    phase: BootPhase = BootPhase.INIT
    container: Container = field(default_factory=Container)
    config: KernelConfig | None = None
    booted_at: float | None = None
    _boot_log: list[str] = field(default_factory=list)

    def boot(self, *, register_defaults: bool = True) -> Kernel:
        """Run the full boot sequence."""
        if self.phase == BootPhase.READY:
            return self

        try:
            self._set_phase(BootPhase.CONFIG)
            self.config = load_config()
            self.container.register(SERVICE_CONFIG, self.config)

            self._set_phase(BootPhase.SERVICES)
            self._register_core_services()
            self._register_decision_log()
            self._register_runtime_services()
            self._register_event_infrastructure()

            if register_defaults:
                self._set_phase(BootPhase.PORTS)
                self._register_default_ports()

            self._set_phase(BootPhase.READY)
            self.booted_at = time.time()
            return self
        except Exception as exc:
            self.phase = BootPhase.INIT
            raise KernelBootError(f"boot failed during {self.phase.value}: {exc}") from exc

    def shutdown(self) -> None:
        """Tear down kernel services."""
        self._set_phase(BootPhase.SHUTDOWN)
        try:
            if self.container.has(SERVICE_EVENT_MESH):
                self.container.resolve(SERVICE_EVENT_MESH).detach()
        except Exception:
            pass
        try:
            if self.container.has(SERVICE_ACTOR_MESH):
                self.container.resolve(SERVICE_ACTOR_MESH).detach()
        except Exception:
            pass
        try:
            if self.container.has(SERVICE_SCHEDULER):
                self.container.resolve(SERVICE_SCHEDULER).stop()
        except Exception:
            pass
        self.container.clear()
        self.config = None
        self.booted_at = None
        self._set_phase(BootPhase.INIT)

    def require_ready(self) -> None:
        if self.phase != BootPhase.READY:
            raise KernelNotReadyError(
                f"kernel not ready (phase={self.phase.value}); call kernel.boot() first"
            )

    def resolve(self, name: str) -> Any:
        self.require_ready()
        return self.container.resolve(name)

    def status(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "booted_at": self.booted_at,
            "services": self.container.names(),
            "workspace": str(self.config.workspace) if self.config else None,
            "base": str(self.config.base) if self.config else None,
            "boot_log": list(self._boot_log),
        }

    def _set_phase(self, phase: BootPhase) -> None:
        self.phase = phase
        self._boot_log.append(phase.value)

    def _register_core_services(self) -> None:
        from kernel import router as kernel_router

        self.container.register(
            SERVICE_ROUTER,
            {
                "detect_tool": kernel_router.detect_tool,
                "run_tool": kernel_router.run_tool,
                "detect_domain": kernel_router.detect_domain,
            },
        )

    def _register_decision_log(self) -> None:
        from kernel.decision_log import DecisionLog

        self.container.register(
            SERVICE_DECISION_LOG,
            lambda: DecisionLog(self.config.base / "data" / "decision_log.db"),
            singleton=True,
        )

    def _register_runtime_services(self) -> None:
        from runtime.service_bus import ServiceBus
        from runtime.services import ServiceManager, default_services
        from runtime.health import HealthMonitor
        from kernel.capability_registry import CapabilityRegistry
        from tools.registry import TOOL_DEFINITIONS

        bus = ServiceBus()
        manager = ServiceManager(bus)
        for spec in default_services():
            manager.register(spec)
        health = HealthMonitor()
        capability_registry = CapabilityRegistry()
        capability_registry.load_manifest_dir(self.config.base / "config" / "capabilities")
        capability_registry.bootstrap_from_tool_definitions(TOOL_DEFINITIONS)

        self.container.register(SERVICE_SERVICE_BUS, bus, singleton=True)
        self.container.register(SERVICE_SERVICE_MANAGER, manager, singleton=True)
        self.container.register(SERVICE_HEALTH_MONITOR, health, singleton=True)
        self.container.register(SERVICE_CAPABILITY_REGISTRY, capability_registry, singleton=True)

        # Optional IPC actor-mesh (C-16) — off by default; socket or nng backend.
        try:
            from runtime.actor_mesh import build_actor_mesh

            actor_cfg = dict(self.config.get("actor_mesh") or {})
            actor_cfg["_service_manager"] = manager
            actor_mesh = build_actor_mesh(bus, cfg=actor_cfg)
            if actor_mesh is not None:
                self.container.register(SERVICE_ACTOR_MESH, actor_mesh, singleton=True)
        except Exception:
            pass

    def _register_event_infrastructure(self) -> None:
        from runtime.event_bus import EventBus
        from runtime.scheduler import Scheduler
        from runtime.workflows import WorkflowEngine

        bus = EventBus()
        scheduler = Scheduler(bus=bus)
        workflow_catalog_path = Path(
            str(
                self.config.get(
                    "workflow_catalog_path",
                    self.config.base / "data" / "workflows" / "catalog.json",
                )
            )
        )
        workflow_store_path = Path(
            str(
                self.config.get(
                    "workflow_store_path",
                    self.config.base / "data" / "workflows" / "runs.db",
                )
            )
        )
        from runtime.workflow_yaml import action_context_from_config

        action_ctx = action_context_from_config(
            dict(self.config.get("workflow_actions") or {}),
            bus=bus,
        )
        workflows = WorkflowEngine(
            bus=bus,
            catalog_path=workflow_catalog_path,
            store_path=workflow_store_path,
            capability_registry=self.container.resolve(SERVICE_CAPABILITY_REGISTRY),
            action_context=action_ctx,
        )

        # Declarative YAML workflows (config/workflows/*.yaml by default).
        try:
            yaml_dir = Path(
                str(
                    self.config.get(
                        "workflow_yaml_dir",
                        self.config.base / "config" / "workflows",
                    )
                )
            )
            if not yaml_dir.is_absolute():
                yaml_dir = self.config.base / yaml_dir
            workflows.load_yaml_dir(yaml_dir)
        except Exception:
            pass

        self.container.register(SERVICE_EVENT_BUS, bus, singleton=True)
        self.container.register(SERVICE_SCHEDULER, scheduler, singleton=True)
        self.container.register(SERVICE_WORKFLOW_ENGINE, workflows, singleton=True)

        # Optional event mesh (off by default). HTTP listen via KERROS_EVENT_MESH_LISTEN.
        try:
            from runtime.event_mesh import build_event_mesh

            mesh_cfg = dict(self.config.get("event_mesh") or {})
            mesh = build_event_mesh(bus, cfg=mesh_cfg, base=self.config.base)
            if mesh is not None:
                self.container.register(SERVICE_EVENT_MESH, mesh, singleton=True)
        except Exception:
            pass

        scheduler.start()

    def _register_default_ports(self) -> None:
        from adapters.tools.claw_adapter import ClawToolAdapter
        from adapters.tools.router_adapter import RouterAdapter
        from adapters.memory.hybrid_memory_adapter import HybridMemoryAdapter
        from adapters.storage.local_fs_adapter import LocalFSAdapter
        from adapters.database.sqlite_adapter import SQLiteAdapter
        from adapters.embeddings.sentence_transformers_adapter import SentenceTransformersAdapter
        from adapters.search.duckduckgo_adapter import DuckDuckGoAdapter

        self.container.register(SERVICE_TOOL_PORT, ClawToolAdapter, singleton=True)
        self.container.register(SERVICE_DISPATCH_PORT, RouterAdapter, singleton=True)
        self.container.register(SERVICE_MEMORY_PORT, HybridMemoryAdapter, singleton=True)

        self.container.register(
            SERVICE_STORAGE_PORT,
            lambda: LocalFSAdapter(base_dir=self.config.base / "data" / "storage" if self.config else None),
            singleton=True,
        )
        self.container.register(
            SERVICE_DATABASE_PORT,
            lambda: SQLiteAdapter(db_path=self.config.base / "data" / "sqlite_db.sqlite" if self.config else None),
            singleton=True,
        )
        self.container.register(
            SERVICE_EMBEDDING_PORT,
            lambda: SentenceTransformersAdapter(
                config=self.config.values if self.config else None
            ),
            singleton=True,
        )
        self.container.register(
            SERVICE_SEARCH_PORT,
            lambda: DuckDuckGoAdapter(),
            singleton=True,
        )

        def _llm_port_factory():
            from adapters.llm.composite_adapter import CompositeLLMAdapter

            return CompositeLLMAdapter()

        self.container.register(SERVICE_LLM_PORT, _llm_port_factory, singleton=True)


# Module-level kernel singleton.
_kernel: Kernel | None = None


def get_kernel() -> Kernel:
    global _kernel
    if _kernel is None:
        _kernel = Kernel()
    return _kernel


def boot(*, register_defaults: bool = True) -> Kernel:
    """Boot the global kernel singleton."""
    return get_kernel().boot(register_defaults=register_defaults)


def shutdown() -> None:
    """Shutdown the global kernel singleton."""
    global _kernel
    if _kernel is not None:
        _kernel.shutdown()


def resolve(name: str) -> Any:
    """Resolve a service from the booted global kernel."""
    return get_kernel().resolve(name)
