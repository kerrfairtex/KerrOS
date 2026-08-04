"""
tools/claw_cli.py
=================
CLI integration for OpenClaw-style tools in chat.

Parses slash commands and dispatches to tools/registry.py.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tools.registry import call_tool, format_result, get_workspace, list_tools, tool_names


def detect_claw_tool(text: str) -> tuple[str | None, dict[str, Any] | None]:
  """Detect explicit claw tool commands from user input."""
  if not text or not text.strip():
    return (None, None)

  raw = text.strip()

  if raw.startswith("/tool "):
    body = raw[6:].strip()
    if not body:
      return (None, None)
    parts = body.split(None, 1)
    name = parts[0]
    if name not in tool_names():
      return (None, None)
    args: dict[str, Any] = {}
    if len(parts) == 2 and parts[1].strip():
      try:
        parsed = json.loads(parts[1])
        if isinstance(parsed, dict):
          args = parsed
        else:
          return (None, None)
      except json.JSONDecodeError:
        return (None, None)
    return (name, args)

  if raw.startswith("/read "):
    path = raw[6:].strip().strip('"').strip("'")
    return ("read", {"path": path}) if path else (None, None)

  if raw.startswith("/write "):
    body = raw[7:].strip()
    if " :: " in body:
      path, content = body.split(" :: ", 1)
      return ("write", {"path": path.strip().strip('"').strip("'"), "content": content})
    path = body.strip('"').strip("'")
    return ("write", {"path": path, "content": ""}) if path else (None, None)

  if raw.startswith("/edit "):
    body = raw[6:].strip()
    if " :: " not in body:
      return (None, None)
    parts = body.split(" :: ")
    if len(parts) < 3:
      return (None, None)
    path = parts[0].strip().strip('"').strip("'")
    old_string = parts[1]
    new_string = parts[2]
    replace_all = False
    if new_string.endswith(" ::all"):
      replace_all = True
      new_string = new_string[:-6]
    return ("edit", {
      "path": path,
      "old_string": old_string,
      "new_string": new_string,
      "replace_all": replace_all,
    })

  if raw.startswith("/exec ") or raw.startswith("/run "):
    cmd = raw.split(" ", 1)[1].strip() if " " in raw else ""
    return ("exec", {"command": cmd}) if cmd else (None, None)

  if raw.startswith("/list") or raw.startswith("/ls"):
    body = raw.split(None, 1)
    path = "."
    recursive = False
    if len(body) > 1:
      arg = body[1].strip()
      if arg == "-r" or arg == "--recursive":
        recursive = True
      elif arg.startswith("-r "):
        recursive = True
        path = arg[3:].strip() or "."
      else:
        path = arg.strip('"').strip("'") or "."
    return ("list", {"path": path, "recursive": recursive})

  if raw.startswith("/remove ") or raw.startswith("/rm "):
    path = raw.split(" ", 1)[1].strip().strip('"').strip("'")
    return ("remove", {"path": path}) if path else (None, None)

  if raw.startswith("/code-index") or raw == "/code_index_build":
    body = raw.split(None, 1)
    root = body[1].strip() if len(body) > 1 else None
    args: dict[str, Any] = {}
    if root:
      args["root"] = root
    return ("code_index_build", args)

  if raw.startswith("/symbols ") or raw.startswith("/code-symbols "):
    query = raw.split(" ", 1)[1].strip().strip('"').strip("'")
    return ("code_symbols", {"query": query}) if query else (None, None)

  if raw.startswith("/code-search ") or raw.startswith("/rg "):
    pattern = raw.split(" ", 1)[1].strip()
    return ("code_search", {"pattern": pattern}) if pattern else (None, None)

  if raw.startswith("/code-rag"):
    # /code-rag [build|full|status] [root]
    # /code-rag ask <query>
    # /code-rag <query>  → retrieve
    body = raw[len("/code-rag") :].strip()
    if not body or body.split()[0] in ("build", "status"):
      args: dict[str, Any] = {}
      parts = body.split()
      if parts and parts[0] == "build":
        if len(parts) > 1 and parts[1] != "full":
          args["root"] = parts[1]
        if "full" in parts:
          args["full"] = True
      return ("code_rag_build", args)
    if body.split()[0] == "full":
      args = {"full": True}
      if len(body.split()) > 1:
        args["root"] = body.split()[1]
      return ("code_rag_build", args)
    if body.startswith("ask "):
      return ("code_rag_ask", {"query": body[4:].strip(), "llm": False})
    if body.startswith("ask-llm "):
      return ("code_rag_ask", {"query": body[8:].strip(), "llm": True})
    return ("code_rag_retrieve", {"query": body})

  if raw in ("/finetune-plan", "/finetune_plan"):
    return ("finetune_plan", {})

  if raw in ("/finetune-export", "/finetune_export"):
    return ("finetune_export", {})

  if raw.startswith("/workspace"):
    return ("__workspace__", {})

  return (None, None)


def run_claw_tool(name: str, args: dict[str, Any] | None = None) -> str:
  """Execute a claw tool and return formatted output."""
  if name == "__workspace__":
    return f"workspace: {get_workspace()}"

  result = call_tool(name, args or {})
  if result.ok:
    prefix = f"[{name}]"
    return f"{prefix} {result.output}" if result.output else f"{prefix} ok"
  return f"[{name}] error: {result.error or result.output or 'unknown error'}"


def claw_tool_help_lines() -> list[tuple[str, str]]:
  return [
    ("/read <path>", "Read a workspace file"),
    ("/write <path> :: <content>", "Write/create a file"),
    ("/edit <path> :: <old> :: <new>", "Replace text in a file"),
    ("/list [path]", "List directory (use -r for recursive)"),
    ("/exec <command>", "Run a shell command"),
    ("/remove <path>", "Delete a file or directory"),
    ("/code-index [root]", "Rebuild code symbol index"),
    ("/symbols <query>", "Search indexed symbols"),
    ("/code-search <pattern>", "Search file contents (rg)"),
    ("/code-rag build|full", "Build Soft code-RAG (ADR-107, incremental)"),
    ("/code-rag <query>", "Hybrid retrieve with citations"),
    ("/code-rag ask <q>", "Cited context (ask-llm for LiteLLM)"),
    ("/finetune-plan", "Plan Unsloth LoRA → GGUF export"),
    ("/finetune-export", "Soft-export GGUF (gated)"),
    ("/tool <name> <json>", "Call any claw tool with JSON args"),
    ("/workspace", "Show active workspace root"),
  ]


def claw_tools_summary() -> str:
  return " · ".join(tool_names())
