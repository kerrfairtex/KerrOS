"""
tools/shell_hooks.py
====================
Shell-script lifecycle hooks (ADR-065).

Config (config.json ``shell_hooks`` or env KERROS_SHELL_HOOKS=1):
  {
    "enabled": true,
    "auto_accept": false,
    "hooks": [
      {"event": "pre_tool_call", "command": "scripts/hooks/pre_tool.py"},
      {"event": "post_tool_call", "command": "scripts/hooks/post_tool.py"},
      {"event": "session_start", "command": "scripts/hooks/session_start.sh"}
    ]
  }

Scripts receive JSON on stdin; pre_tool scripts may print
{"decision":"block","reason":"..."} to deny. Commands are argv-split
(shell=False) and must stay under the workspace.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Optional

from tools.claw_tools import get_workspace

_registered = False


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _cfg() -> dict[str, Any]:
    try:
        from core.config import cfg

        block = cfg().get("shell_hooks")
        return block if isinstance(block, dict) else {}
    except Exception:
        return {}


def is_enabled() -> bool:
    env = os.environ.get("KERROS_SHELL_HOOKS")
    if env is not None:
        return _truthy(env)
    return _truthy(_cfg().get("enabled", False))


def _resolve_command(command: str) -> Optional[list[str]]:
    parts = shlex.split(os.path.expanduser(command or ""))
    if not parts:
        return None
    root = get_workspace().resolve()
    prog = Path(parts[0])
    if not prog.is_absolute():
        prog = (root / prog).resolve()
    else:
        prog = prog.resolve()
    if not str(prog).startswith(str(root)):
        return None
    if not prog.is_file():
        return None
    if prog.suffix == ".py":
        return ["python3", str(prog), *parts[1:]]
    return [str(prog), *parts[1:]]


def run_shell_hook(event: str, payload: dict[str, Any], command: str) -> dict[str, Any]:
    argv = _resolve_command(command)
    if not argv:
        return {"ok": False, "error": "command not under workspace or missing"}
    try:
        proc = subprocess.run(
            argv,
            input=json.dumps({"hook_event_name": event, **payload}),
            text=True,
            capture_output=True,
            timeout=15,
            cwd=str(get_workspace()),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    out = (proc.stdout or "").strip()
    decision = {"ok": proc.returncode == 0, "stdout": out[:2000], "returncode": proc.returncode}
    if out.startswith("{"):
        try:
            parsed = json.loads(out)
            if isinstance(parsed, dict):
                decision["parsed"] = parsed
        except Exception:
            pass
    return decision


def register_shell_hooks() -> dict[str, Any]:
    """Wire configured shell hooks into tool + session hook registries."""
    global _registered
    if _registered or not is_enabled():
        return {"ok": True, "registered": _registered, "enabled": is_enabled()}
    block = _cfg()
    hooks = block.get("hooks") or []
    if not isinstance(hooks, list):
        return {"ok": False, "error": "shell_hooks.hooks must be a list"}
    from core.session_hooks import register_session_hook
    from tools.tool_hooks import register_post_tool_call, register_pre_tool_call

    count = 0
    for i, item in enumerate(hooks):
        if not isinstance(item, dict):
            continue
        event = str(item.get("event") or "")
        command = str(item.get("command") or "")
        if not event or not command:
            continue
        name = f"shell_hook_{i}_{event}"

        if event == "pre_tool_call":

            def _pre(tool, args, _cmd=command):
                res = run_shell_hook(
                    "pre_tool_call",
                    {"tool_name": tool, "tool_input": args},
                    _cmd,
                )
                parsed = res.get("parsed") or {}
                decision = str(parsed.get("decision") or parsed.get("action") or "").lower()
                if decision == "block":
                    return False, str(parsed.get("reason") or parsed.get("message") or "blocked by shell hook")
                return True, "ok"

            register_pre_tool_call(name, _pre)
            count += 1
        elif event == "post_tool_call":

            def _post(tool, args, result, _cmd=command):
                run_shell_hook(
                    "post_tool_call",
                    {"tool_name": tool, "tool_input": args, "result": str(result)[:1000]},
                    _cmd,
                )

            register_post_tool_call(name, _post)
            count += 1
        elif event in ("session_start", "session_end", "turn_start", "turn_end"):

            def _sess(payload, _cmd=command, _ev=event):
                run_shell_hook(_ev, payload, _cmd)

            register_session_hook(event, name, _sess)
            count += 1
    _registered = True
    return {"ok": True, "registered": True, "count": count}
