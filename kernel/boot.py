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
    SERVICE_LLM_PORT,
    SERVICE_MEMORY_PORT,
    SERVICE_ROUTER,
    SERVICE_TOOL_PORT,
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

    def _register_default_ports(self) -> None:
        from adapters.tools.claw_adapter import ClawToolAdapter
        from adapters.tools.router_adapter import RouterAdapter
        from adapters.memory.rag_store_adapter import RagStoreAdapter

        self.container.register(SERVICE_TOOL_PORT, ClawToolAdapter, singleton=True)
        self.container.register(SERVICE_DISPATCH_PORT, RouterAdapter, singleton=True)
        self.container.register(SERVICE_MEMORY_PORT, RagStoreAdapter, singleton=True)

        def _llm_port_factory():
            from adapters.llm.multi_api_adapter import MultiAPIAdapter

            return MultiAPIAdapter()

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
