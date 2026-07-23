"""
kernel package — P0 KerrOS kernel foundation.

Public surface:
    from kernel import boot, get_kernel, resolve, KernelConfig
    from kernel.contract import BootPhase, SERVICE_*
"""

from kernel.boot import boot, get_kernel, resolve, shutdown
from kernel.config import KernelConfig, load_config, reload_config
from kernel.container import Container
from kernel.contract import (
    BootPhase,
    KernelBootError,
    KernelError,
    KernelNotReadyError,
    SERVICE_CONFIG,
    SERVICE_LLM_PORT,
    SERVICE_ROUTER,
    SERVICE_TOOL_PORT,
)

__all__ = [
    "BootPhase",
    "Container",
    "KernelBootError",
    "KernelConfig",
    "KernelError",
    "KernelNotReadyError",
    "SERVICE_CONFIG",
    "SERVICE_LLM_PORT",
    "SERVICE_ROUTER",
    "SERVICE_TOOL_PORT",
    "boot",
    "get_kernel",
    "load_config",
    "reload_config",
    "resolve",
    "shutdown",
]
