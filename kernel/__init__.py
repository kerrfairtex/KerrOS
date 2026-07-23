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
    SERVICE_DECISION_LOG,
    SERVICE_DISPATCH_PORT,
    SERVICE_EVENT_BUS,
    SERVICE_HEALTH_MONITOR,
    SERVICE_LLM_PORT,
    SERVICE_MEMORY_PORT,
    SERVICE_ROUTER,
    SERVICE_SCHEDULER,
    SERVICE_SERVICE_MANAGER,
    SERVICE_TOOL_PORT,
    SERVICE_WORKFLOW_ENGINE,
)
from kernel.decision_log import DecisionLog, get_decision_log, record_decision
from kernel.access import (
    detect_tool,
    run_tool,
    detect_domain,
    memory_query,
    get_event_bus,
    get_llm_port,
    get_dispatch_port,
    get_memory_port,
    get_scheduler,
    get_workflow_engine,
)

__all__ = [
    "BootPhase",
    "Container",
    "DecisionLog",
    "KernelBootError",
    "KernelConfig",
    "KernelError",
    "KernelNotReadyError",
    "SERVICE_CONFIG",
    "SERVICE_DECISION_LOG",
    "SERVICE_DISPATCH_PORT",
    "SERVICE_EVENT_BUS",
    "SERVICE_HEALTH_MONITOR",
    "SERVICE_LLM_PORT",
    "SERVICE_MEMORY_PORT",
    "SERVICE_ROUTER",
    "SERVICE_SCHEDULER",
    "SERVICE_SERVICE_MANAGER",
    "SERVICE_TOOL_PORT",
    "SERVICE_WORKFLOW_ENGINE",
    "boot",
    "get_decision_log",
    "get_kernel",
    "load_config",
    "record_decision",
    "reload_config",
    "resolve",
    "shutdown",
    "detect_tool",
    "run_tool",
    "detect_domain",
    "memory_query",
    "get_event_bus",
    "get_llm_port",
    "get_dispatch_port",
    "get_memory_port",
    "get_scheduler",
    "get_workflow_engine",
]
