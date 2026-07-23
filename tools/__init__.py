"""
tools package — KerrOS system capabilities.

OpenClaw-style filesystem and execution tools:
    from tools import list_tools, call_tool, ClawToolAdapter
"""

from tools.claw_tools import (
    ClawToolError,
    ToolResult,
    apply_patch,
    edit,
    exec_cmd,
    get_workspace,
    list_dir,
    read,
    remove,
    write,
)
from tools.registry import (
    call_tool,
    call_tool_json,
    format_result,
    get_tool_schema,
    list_tools,
    tool_names,
    workspace_info,
)

__all__ = [
    "ClawToolError",
    "ToolResult",
    "apply_patch",
    "call_tool",
    "call_tool_json",
    "edit",
    "exec_cmd",
    "format_result",
    "get_tool_schema",
    "get_workspace",
    "list_dir",
    "list_tools",
    "read",
    "remove",
    "tool_names",
    "workspace_info",
    "write",
]
