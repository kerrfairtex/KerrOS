"""
ports/tool_port.py
==================
ToolPort — stable interface for tool-related adapters.
"""

from typing import Any, Protocol


class ToolPort(Protocol):
    def dispatch(self, intent: str, payload: Any = None) -> Any:
        """Route kernel tool intents via adapter dispatch."""
        ...

    def detect_tool(self, text: str, *, bypass_gate: bool = False):
        ...

    def run_tool(self, tool: str, args: Any):
        ...

    def detect_domain(self, text: str):
        ...

    def list_tools(self) -> list[dict[str, Any]]:
        """Return tool schemas for LLM function calling."""
        ...

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a tool and return a structured result dict."""
        ...

    def workspace(self) -> str:
        """Return the active workspace root path."""
        ...
