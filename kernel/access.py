"""
kernel/access.py
================
Port access facades with kernel-first, direct-import fallback (KOS-014).
"""

from __future__ import annotations

import os
from typing import Any


def _kernel_ready() -> bool:
    try:
        from kernel.boot import get_kernel
        from kernel.contract import BootPhase

        return get_kernel().phase == BootPhase.READY
    except Exception:
        return False


def _resolve(name: str) -> Any:
    from kernel.boot import get_kernel

    return get_kernel().container.resolve(name)


def get_llm_port():
    if _kernel_ready():
        try:
            return _resolve("llm_port")
        except Exception:
            pass
    from adapters.llm.composite_adapter import CompositeLLMAdapter

    return CompositeLLMAdapter()


def get_event_bus():
    if _kernel_ready():
        try:
            return _resolve("event_bus")
        except Exception:
            pass
    from runtime.event_bus import EventBus

    return EventBus()


def get_scheduler():
    if _kernel_ready():
        try:
            return _resolve("scheduler")
        except Exception:
            pass
    from runtime.scheduler import Scheduler

    return Scheduler()


def get_workflow_engine():
    if _kernel_ready():
        try:
            return _resolve("workflow_engine")
        except Exception:
            pass
    from runtime.workflows import WorkflowEngine

    return WorkflowEngine()


def get_capability_registry():
    if _kernel_ready():
        try:
            return _resolve("capability_registry")
        except Exception:
            pass
    from kernel.capability_registry import CapabilityRegistry

    return CapabilityRegistry()


def get_dispatch_port():
    if _kernel_ready():
        try:
            return _resolve("dispatch_port")
        except Exception:
            pass
    from adapters.tools.router_adapter import RouterAdapter

    return RouterAdapter()


def get_memory_port():
    if _kernel_ready():
        try:
            return _resolve("memory_port")
        except Exception:
            pass
    from adapters.memory.hybrid_memory_adapter import HybridMemoryAdapter

    return HybridMemoryAdapter()


def detect_tool(text: str, bypass_gate: bool = False):
    return get_dispatch_port().detect_tool(text, bypass_gate=bypass_gate)


def run_tool(tool: str, args: Any):
    return get_dispatch_port().run_tool(tool, args)


def detect_domain(text: str):
    return get_dispatch_port().detect_domain(text)


def memory_query(text: str, *, top_k: int = 5) -> list[tuple[int, str, str]]:
    try:
        from memory.base import MemoryService

        return MemoryService().query(text, top_k=top_k)
    except Exception:
        return []


def memory_upsert(text: str, source: str, metadata: dict | None = None) -> None:
    try:
        from memory.base import MemoryService

        MemoryService().upsert(text, source, metadata)
    except Exception:
        pass


def memory_ingest_file(path: str) -> None:
    """Read a file from disk and upsert its contents into the knowledge store."""
    try:
        from memory.service import MemoryService

        MemoryService().ingest_file(path)
    except Exception:
        pass


def memory_list_sources() -> list[str]:
    try:
        from memory.base import MemoryService

        return MemoryService().list_sources()
    except Exception:
        return []


def memory_search_by_category(query: str, category: str | None = None, top_k: int = 4):
    try:
        from memory.base import MemoryService

        return MemoryService().search_by_category(query, category, top_k)
    except Exception:
        return []


def memory_search_multi_category(query: str, categories: list[str], top_k: int = 4):
    try:
        from memory.base import MemoryService

        return MemoryService().search_multi_category(query, categories, top_k)
    except Exception:
        return []


def memory_search_exact_id(query: str):
    try:
        from memory.base import MemoryService

        return MemoryService().search_exact_id(query)
    except Exception:
        return []


def llm_complete(
    prompt: str,
    system: str | None = None,
    history: list | None = None,
    max_tokens: int = 1024,
    **kwargs,
) -> str:
    return get_llm_port().complete(
        prompt,
        system=system,
        history=history,
        max_tokens=max_tokens,
        **kwargs,
    )
