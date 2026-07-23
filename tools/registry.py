"""
tools/registry.py
=================
OpenClaw-style tool registry: JSON schemas + dispatch.

Agents and LLM providers can call list_tools() for function definitions
and call_tool(name, args) to execute them.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from tools.claw_tools import (
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

Handler = Callable[..., ToolResult]

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a file from the workspace. Returns numbered lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "offset": {"type": "integer", "description": "1-based line to start reading", "default": 1},
                    "limit": {"type": "integer", "description": "Max lines to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Create or overwrite a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "content": {"type": "string", "description": "Full file contents"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Replace text in a file. Use replace_all for multiple occurrences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "old_string": {"type": "string", "description": "Exact text to find"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "replace_all": {"type": "boolean", "default": False},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list",
            "description": "List files and directories in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path", "default": "."},
                    "recursive": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exec",
            "description": "Run a shell command in the workspace. Commands must be in config.json safe_commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "cwd": {"type": "string", "description": "Working directory relative to workspace"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply a unified diff patch to workspace files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {"type": "string", "description": "Unified diff patch text"},
                },
                "required": ["patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove",
            "description": "Delete a file or directory in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete"},
                },
                "required": ["path"],
            },
        },
    },
]

_HANDLERS: dict[str, Handler] = {
    "read": read,
    "write": write,
    "edit": edit,
    "list": list_dir,
    "exec": exec_cmd,
    "apply_patch": apply_patch,
    "remove": remove,
}


def list_tools() -> list[dict[str, Any]]:
    """Return OpenAI-compatible tool definitions."""
    return [dict(t) for t in TOOL_DEFINITIONS]


def tool_names() -> list[str]:
    return list(_HANDLERS.keys())


def get_tool_schema(name: str) -> dict[str, Any] | None:
    for tool in TOOL_DEFINITIONS:
        fn = tool.get("function", {})
        if fn.get("name") == name:
            return dict(tool)
    return None


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
    """Dispatch a tool call by name with keyword arguments."""
    handler = _HANDLERS.get(name)
    if not handler:
        return ToolResult(False, name or "unknown", error=f"unknown tool: {name}")

    args = arguments or {}
    try:
        return handler(**args)
    except TypeError as e:
        return ToolResult(False, name, error=f"invalid arguments: {e}")


def call_tool_json(name: str, arguments_json: str) -> ToolResult:
    """Dispatch a tool call with JSON-encoded arguments."""
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        return ToolResult(False, name, error=f"invalid JSON arguments: {e}")
    if not isinstance(args, dict):
        return ToolResult(False, name, error="arguments must be a JSON object")
    return call_tool(name, args)


def format_result(result: ToolResult) -> str:
    """Human-readable result for chat/CLI display."""
    if result.ok:
        return result.output or "[ok]"
    if result.error and result.output:
        return f"[error] {result.error}\n{result.output}"
    return f"[error] {result.error or 'unknown error'}"


def workspace_info() -> dict[str, str]:
    return {"workspace": str(get_workspace())}
