"""
kernel/compat.py
================
Compatibility aliases for older or cross-module import paths.

This file does NOT modify package ``__init__`` behavior. It simply provides
stable import targets that other modules can rely on during incremental
refactors, without changing existing runtime semantics.

Preferred new style:
    from kernel.compat import generate_complete, looks_truncated
    from memory.service import MemoryService  # noqa: F401
"""

from __future__ import annotations

import importlib
from typing import Any


def _resolve(path: str) -> Any:
    module_path, _, attr = path.rpartition(".")
    if not module_path:
        raise ImportError(f"invalid compat target: {path}")
    module = importlib.import_module(module_path)
    return getattr(module, attr)


def _lazy(path: str, name: str) -> Any:
    """Resolve an attribute only when accessed."""

    def _load():
        return _resolve(path)

    return _load


# completion runtime aliases --------------------------------------------------
# Old/core-local references often point to completion modules under core/.
# We keep compatibility here rather than renaming modules globally.
completion_authority = _lazy("core.completion_authority.CompletionAuthority", "completion_authority")
completion_consensus = _lazy("core.completion_consensus.CompletionConsensus", "completion_consensus")
completion_control_plane = _lazy("core.completion_control_plane.CompletionControlPlane", "completion_control_plane")
completion_decision = _lazy("core.completion_decision.CompletionDecision", "completion_decision")
completion_diagnostics = _lazy("core.completion_diagnostics.CompletionDiagnostics", "completion_diagnostics")
completion_event_bus = _lazy("core.completion_event_bus.CompletionEventBus", "completion_event_bus")
completion_event_integration = _lazy("core.completion_event_integration.CompletionEventIntegration", "completion_event_integration")
completion_observability = _lazy("core.completion_observability.CompletionObservability", "completion_observability")
completion_recovery = _lazy("core.completion_recovery.CompletionRecovery", "completion_recovery")
completion_runtime = _lazy("core.completion_runtime.CompletionRuntime", "completion_runtime")
completion_runtime_api = _lazy("core.completion_runtime_api.CompletionRuntimeAPI", "completion_runtime_api")
completion_runtime_coordinator = _lazy("core.completion_runtime_coordinator.CompletionRuntimeCoordinator", "completion_runtime_coordinator")
completion_runtime_kernel = _lazy("core.completion_runtime_kernel.CompletionRuntimeKernel", "completion_runtime_kernel")

# completion functional aliases -----------------------------------------------
# Centralize access to completion helpers so callers do not need to know
# whether the implementation lives in core/complete.py or elsewhere.
generate_complete = _resolve("core.complete.generate_complete")
looks_truncated = _resolve("core.complete.looks_truncated")


# gateway/kernel bridge aliases -----------------------------------------------
# Preserve older cross-folder access patterns without importing gateway/ directly.
class _GatewayShim:
    router = None
    provider = None

    @staticmethod
    def _try_import():
        try:
            from gateway.webhooks import router as router  # noqa: PLC0415

            _GatewayShim.router = router
        except Exception:  # pragma: no cover - optional gateway path
            pass
        try:
            from gateway.provider import provider as provider  # noqa: PLC0415

            _GatewayShim.provider = provider
        except Exception:  # pragma: no cover
            pass


_GatewayShim._try_import()
gateway_router = _GatewayShim.router
gateway_provider = _GatewayShim.provider


# config aliases --------------------------------------------------------------
# Provide stable names without forcing all call sites onto one object shape.
cfg = _resolve("kernel.config.load_config")().values


__all__ = [
    "completion_authority",
    "completion_consensus",
    "completion_control_plane",
    "completion_decision",
    "completion_diagnostics",
    "completion_event_bus",
    "completion_event_integration",
    "completion_observability",
    "completion_recovery",
    "completion_runtime",
    "completion_runtime_api",
    "completion_runtime_coordinator",
    "completion_runtime_kernel",
    "generate_complete",
    "looks_truncated",
    "gateway_router",
    "gateway_provider",
    "cfg",
]
