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
    code_index_build,
    code_search,
    code_symbols,
    edit,
    exec_cmd,
    finetune_export,
    finetune_plan,
    get_workspace,
    list_dir,
    read,
    remove,
    write,
)
from tools.skill_tools import skill_manage, skill_view, skills_list

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
    {
        "type": "function",
        "function": {
            "name": "code_index_build",
            "description": "Rebuild the workspace code symbol index (Phase C / ADR-052).",
            "parameters": {
                "type": "object",
                "properties": {
                    "root": {
                        "type": "string",
                        "description": "Optional subdirectory relative to workspace",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_symbols",
            "description": "Search indexed code symbols by name substring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Symbol name substring"},
                    "top_k": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_search",
            "description": "Search workspace file contents (ripgrep when available).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern / regex"},
                    "top_k": {"type": "integer", "default": 20},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finetune_plan",
            "description": "Plan Unsloth LoRA → GGUF Q4_K_M export (Fake by default; ADR-053).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finetune_export",
            "description": "Soft-export finetuned weights to GGUF (gated; dry-run unless allow_export).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # ------------------------------------------------------------------
    # Hermes-style Progressive Disclosure skill tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "skills_list",
            "description": (
                "Return a compact index of all available skills (name, category, description). "
                "Inject this at session start (Level 0) to orient the agent without loading full docs. "
                "Optionally filter by category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category name (e.g. 'web_stack', 'ai_patterns', 'tool_catalog').",
                    },
                },
            },
        },
    },    {
        "type": "function",
        "function": {
            "name": "skill_view",
            "description": (
                "Load the full content of a skill by name (Level 1). "
                "Call this when the agent needs detailed guidance for a specific skill. "
                "Optionally supply file_path to load a specific reference file directly (Level 2)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill stem name, e.g. 'auth_patterns' or 'fullstack.backend'.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Explicit file path relative to workspace (overrides name lookup).",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_manage",
            "description": (
                "Create, update, or delete a skill (Dynamic Evolution). "
                "Agents use this to persist newly discovered workflows as reusable skills. "
                "Actions: 'save' (write skill content) or 'delete' (remove a skill)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["save", "delete"],
                        "description": "Operation to perform.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill stem name (snake_case, no extension).",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown content for the skill (required for save).",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category subdirectory. Defaults to 'custom'.",
                    },
                    "description": {
                        "type": "string",
                        "description": "One-line summary shown in skills_list index.",
                    },
                },
                "required": ["action", "name"],
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
    "code_index_build": code_index_build,
    "code_symbols": code_symbols,
    "code_search": code_search,
    "finetune_plan": finetune_plan,
    "finetune_export": finetune_export,
    # Hermes-style skill tools
    "skills_list": skills_list,
    "skill_view": skill_view,
    "skill_manage": skill_manage,
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
