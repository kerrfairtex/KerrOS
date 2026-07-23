"""
kernel/contract.py
==================
P0 kernel contract — stable names, lifecycle phases, and error types.

The kernel contract defines the boundary between kernel services and
everything else (ports, adapters, agents, CLI). Callers should depend on
these symbols rather than reaching into implementation modules directly.
"""

from __future__ import annotations

from enum import Enum


class BootPhase(str, Enum):
    """Ordered boot lifecycle phases."""

    INIT = "init"
    CONFIG = "config"
    SERVICES = "services"
    PORTS = "ports"
    READY = "ready"
    SHUTDOWN = "shutdown"


# Registered service names in the DI container.
SERVICE_CONFIG = "config"
SERVICE_LLM_PORT = "llm_port"
SERVICE_TOOL_PORT = "tool_port"
SERVICE_MEMORY_PORT = "memory_port"
SERVICE_DISPATCH_PORT = "dispatch_port"
SERVICE_DECISION_LOG = "decision_log"
SERVICE_SERVICE_MANAGER = "service_manager"
SERVICE_HEALTH_MONITOR = "health_monitor"
SERVICE_ROUTER = "router"

# Port registration keys used during boot.
PORT_LLM = SERVICE_LLM_PORT
PORT_TOOL = SERVICE_TOOL_PORT
PORT_MEMORY = SERVICE_MEMORY_PORT
PORT_DISPATCH = SERVICE_DISPATCH_PORT

# Minimum phase required for common operations.
MIN_PHASE_READY = BootPhase.READY


class KernelError(Exception):
    """Base kernel error."""


class KernelNotReadyError(KernelError):
    """Raised when the kernel has not reached READY phase."""


class KernelBootError(KernelError):
    """Raised when boot fails at any phase."""


class ServiceNotFoundError(KernelError):
    """Raised when a service is not registered in the container."""


class ServiceAlreadyRegisteredError(KernelError):
    """Raised when registering a duplicate service name."""
