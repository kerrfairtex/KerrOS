"""
ports/dispatch_port.py
======================
DispatchPort — stable interface for kernel tool routing (KOS-007).
"""

from typing import Any, Protocol


class DispatchPort(Protocol):
    def dispatch(self, intent: str, payload: Any = None) -> Any:
        """Route an intent (detect_tool, run_tool, detect_domain) to the kernel."""
        ...

    def detect_tool(self, text: str, *, bypass_gate: bool = False):
        ...

    def run_tool(self, tool: str, args: Any):
        ...

    def detect_domain(self, text: str):
        ...
