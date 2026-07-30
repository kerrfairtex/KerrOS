"""
tools/exec_approval.py
======================
Dangerous-command detection for claw exec / bash (ADR-062).

Integrates as a pre-tool hook. Does not replace scope_gate — runs after it
for shell-like tools. Default: deny dangerous patterns unless
KERROS_EXEC_APPROVE=1 (session allow) or pattern is allowlisted in config.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any, Optional

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+(-[^\s]*\s+)*/", "delete in root path"),
    (r"\brm\s+-[^\s]*r", "recursive delete"),
    (r"\brm\s+--recursive\b", "recursive delete (long flag)"),
    (r"\bmkfs\b", "format filesystem"),
    (r"\bdd\s+.*if=", "disk copy"),
    (r">\s*/dev/sd", "write to block device"),
    (r"\bchmod\s+(-[^\s]*\s+)*(777|666)\b", "world-writable permissions"),
    (r"\bchown\s+(-[^\s]*)?R\s+root", "recursive chown to root"),
    (r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;", "fork bomb"),
    (r"\bcurl\s+[^|]*\|\s*(?:ba)?sh", "pipe remote script to shell"),
    (r"\bwget\s+[^|]*\|\s*(?:ba)?sh", "pipe remote script to shell"),
    (r"\bshutdown\b|\breboot\b|\bhalt\b", "system power control"),
    (r"\bmkfs\.|\bwipefs\b", "destructive disk util"),
]

_compiled = [(re.compile(p, re.I), reason) for p, reason in DANGEROUS_PATTERNS]
_session_allow: set[str] = set()
_lock = threading.Lock()


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def detect_dangerous_command(command: str) -> Optional[str]:
    text = command or ""
    for rx, reason in _compiled:
        if rx.search(text):
            return reason
    return None


def allow_for_session(fingerprint: str) -> None:
    with _lock:
        _session_allow.add(fingerprint)


def _fp(command: str) -> str:
    return re.sub(r"\s+", " ", (command or "").strip())[:240]


def check_exec_approval(tool: str, args: Any) -> tuple[bool, str]:
    """Return (allowed, reason). Soft-pass when feature disabled."""
    if not _truthy(os.environ.get("KERROS_EXEC_GUARD", "1")):
        return True, "exec guard off"
    if tool not in ("bash", "exec", "self_run"):
        return True, "n/a"
    # args may be str or list
    if isinstance(args, (list, tuple)):
        cmd = " ".join(str(a) for a in args)
    else:
        cmd = str(args or "")
    reason = detect_dangerous_command(cmd)
    if not reason:
        return True, "ok"
    fp = _fp(cmd)
    with _lock:
        if fp in _session_allow:
            return True, "session allow"
    if _truthy(os.environ.get("KERROS_EXEC_APPROVE")):
        allow_for_session(fp)
        return True, "auto-approved via KERROS_EXEC_APPROVE"
    return False, f"dangerous command blocked ({reason}); set KERROS_EXEC_APPROVE=1 or /approve-exec"


def register_exec_approval_hook() -> None:
    from tools.tool_hooks import register_pre_tool_call

    def _pre(tool, args):
        ok, reason = check_exec_approval(tool, args)
        return ok, reason

    register_pre_tool_call("exec_approval", _pre)
