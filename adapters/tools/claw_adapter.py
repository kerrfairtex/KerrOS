"""
adapters/tools/claw_adapter.py
==============================
ClawToolAdapter — ToolPort implementation over OpenClaw-style tools.
"""

from __future__ import annotations

from typing import Any

from tools.registry import call_tool, format_result, get_workspace, list_tools


class ClawToolAdapter:
    """Adapter that exposes tools/registry.py through the ToolPort interface."""

    def list_tools(self) -> list[dict[str, Any]]:
        return list_tools()

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = call_tool(name, arguments)
        payload = result.to_dict()
        payload["formatted"] = format_result(result)
        return payload

    def workspace(self) -> str:
        return str(get_workspace())
