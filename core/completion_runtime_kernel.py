"""
DEPRECATED — use core.completion_runtime_coordinator (KOS-015).

This module re-exports the renamed completion runtime coordinator to
avoid breaking existing imports. The name "kernel" here refers to the
completion pipeline coordinator, not kernel/.
"""
import warnings

warnings.warn(
    "core.completion_runtime_kernel is deprecated; use core.completion_runtime_coordinator",
    DeprecationWarning,
    stacklevel=2,
)

from core.completion_runtime_coordinator import (
    CompletionRuntimeCoordinator,
    coordinator,
    execute,
)

# Backward-compatible aliases
CompletionRuntimeKernel = CompletionRuntimeCoordinator
kernel = coordinator

__all__ = [
    "CompletionRuntimeCoordinator",
    "CompletionRuntimeKernel",
    "coordinator",
    "kernel",
    "execute",
]
