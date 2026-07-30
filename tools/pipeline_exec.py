"""
tools/pipeline_exec.py
======================
Hermes-style pipeline collapsing (ADR-060): run a short Python script that
calls allowlisted KerrOS tools via RPC-style helpers, in a subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from typing import Any

# Tools callable from a pipeline script (passive / diagnostic only).
# Offensive + deploy stay out — must use normal gated chat path.
PIPELINE_ALLOWLIST = frozenset(
    {
        "calc",
        "sysinfo",
        "file_read",
        "nav",
        "scan",
        "search_past_sessions",
        "skills_curate",
    }
)

_RUNNER = r'''
import json, sys
from kernel.router import run_tool

ALLOW = set(json.loads(sys.argv[1]))
script = sys.stdin.read()

def call(tool, args=""):
    tool = str(tool)
    if tool not in ALLOW:
        raise PermissionError(f"tool not allowlisted in pipeline: {tool}")
    return run_tool(tool, args)

ns = {"call": call, "run_tool": call, "__name__": "__pipeline__"}
exec(compile(script, "<pipeline>", "exec"), ns, ns)
if "result" in ns:
    print(ns["result"])
'''


def execute_pipeline(script: str, *, timeout: int = 20) -> str:
    code = (script or "").strip()
    if not code:
        return "[pipeline] empty script"
    if len(code) > 12_000:
        return "[pipeline] script too large"
    # Block obvious escapes.
    banned = ("os.system", "subprocess", "socket", "eval(", "__import__", "open(")
    lower = code.lower()
    for b in banned:
        if b in lower and "call(" not in b:
            # allow call( but not open(/subprocess
            if b.startswith("call"):
                continue
            return f"[pipeline] blocked pattern: {b}"
    for b in ("os.system", "subprocess", "socket", "eval(", "__import__"):
        if b in lower:
            return f"[pipeline] blocked pattern: {b}"
    if "open(" in lower:
        return "[pipeline] blocked pattern: open("

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.expanduser("~/offline_ai") + os.pathsep + env.get(
        "PYTHONPATH", ""
    )
    try:
        proc = subprocess.run(
            [
                os.environ.get("PYTHON", "python3"),
                "-c",
                _RUNNER,
                json.dumps(sorted(PIPELINE_ALLOWLIST)),
            ],
            input=code,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout)),
            cwd=os.path.expanduser("~/offline_ai"),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "[pipeline] timeout"
    except Exception as exc:
        return f"[pipeline] error: {exc}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return f"[pipeline] exit {proc.returncode}\n{err or out}"[:2000]
    return out or "[pipeline] ok (no output)"
