"""adapters/integrations package — soft integration catalog (ADR-055)."""

from adapters.integrations.registry import (
    adaptive_coding_enabled,
    catalog_status,
    format_status_lines,
    list_tiers,
    load_registry,
    prefer_task_tier,
    resolve_for_task,
    resolve_tier,
)

__all__ = [
    "adaptive_coding_enabled",
    "catalog_status",
    "format_status_lines",
    "list_tiers",
    "load_registry",
    "prefer_task_tier",
    "resolve_for_task",
    "resolve_tier",
]
