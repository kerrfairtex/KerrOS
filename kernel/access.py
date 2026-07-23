"""
kernel/access.py
================
Port access facades with kernel-first, direct-import fallback (KOS-014).
"""

from __future__ import annotations

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
    from adapters.memory.rag_store_adapter import RagStoreAdapter

    return RagStoreAdapter()


def detect_tool(text: str, bypass_gate: bool = False):
    return get_dispatch_port().detect_tool(text, bypass_gate=bypass_gate)


def run_tool(tool: str, args: Any):
    return get_dispatch_port().run_tool(tool, args)


def detect_domain(text: str):
    return get_dispatch_port().detect_domain(text)


def memory_query(text: str, *, top_k: int = 5) -> list[tuple[str, str, str]]:
    return get_memory_port().query(text, top_k=top_k)


def memory_upsert(text: str, source: str, metadata: dict | None = None) -> None:
    get_memory_port().upsert(text, source, metadata)


def memory_list_sources() -> list[str]:
    port = get_memory_port()
    if hasattr(port, "list_sources"):
        return port.list_sources()
    from rag.store import list_sources
    return list_sources()


def memory_search_by_category(query: str, category: str | None = None, top_k: int = 4):
    port = get_memory_port()
    if hasattr(port, "search_by_category"):
        return port.search_by_category(query, category, top_k)
    from rag.store import search_by_category
    return search_by_category(query, category, top_k)


def memory_search_multi_category(query: str, categories: list[str], top_k: int = 4):
    port = get_memory_port()
    if hasattr(port, "search_multi_category"):
        return port.search_multi_category(query, categories, top_k)
    from rag.store import search_multi_category
    return search_multi_category(query, categories, top_k)


def memory_search_exact_id(query: str):
    port = get_memory_port()
    if hasattr(port, "search_exact_id"):
        return port.search_exact_id(query)
    from rag.store import search_exact_id
    return search_exact_id(query)


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
