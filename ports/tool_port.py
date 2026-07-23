"""
ports/tool_port.py
==================
ToolPort — stable interface for agent filesystem and execution tools.

Phase 1: implemented by adapters/tools/claw_adapter.py over tools/registry.py.
"""

from typing import Any, Protocol


class ToolPort(Protocol):
    def list_tools(self) -> list[dict[str, Any]]:
        """Return tool schemas for LLM function calling."""
        ...

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a tool and return a structured result dict."""
        ...

    def workspace(self) -> str:
        """Return the active workspace root path."""
        ...
