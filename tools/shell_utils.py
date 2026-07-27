"""
tools/shell_utils.py
====================
Safe subprocess helpers — shell=False by default, input sanitization.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from typing import Mapping, Sequence

# Characters/operators that require a shell — rejected for user-facing exec.
_SHELL_META_RE = re.compile(r"[|&;<>$`\\]|&&|\|\||\$\(|\$\{")

# Hostnames, domains, IPs — conservative allowlist for network tool args.
_TARGET_RE = re.compile(r"^[a-zA-Z0-9._:-]{1,253}$")

# Repo/branch/event tokens for deploy helpers.
_TOKEN_RE = re.compile(r"^[a-zA-Z0-9._/@:-]{1,200}$")


class ShellCommandError(ValueError):
    pass


def contains_shell_metacharacters(command: str) -> bool:
    return bool(_SHELL_META_RE.search(command))


def sanitize_target(value: str, *, label: str = "target") -> str:
    v = str(value or "").strip()
    if not v or not _TARGET_RE.match(v):
        raise ShellCommandError(f"invalid {label}: {value!r}")
    return v


def sanitize_token(value: str, *, label: str = "value") -> str:
    v = str(value or "").strip()
    if not v or not _TOKEN_RE.match(v):
        raise ShellCommandError(f"invalid {label}: {value!r}")
    return v


def split_command(command: str) -> list[str]:
    cmd = str(command or "").strip()
    if not cmd:
        raise ShellCommandError("command is required")
    if contains_shell_metacharacters(cmd):
        raise ShellCommandError(
            "shell metacharacters are not allowed (use a single command without | ; & > <)"
        )
    return shlex.split(cmd)


def run_argv(
    argv: Sequence[str],
    *,
    timeout: float = 15,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    input_text: str = "",
    max_output: int = 2000,
) -> str:
    try:
        r = subprocess.run(
            list(argv),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            input=input_text,
        )
        out = (r.stdout or r.stderr or "[No output]").strip()
        return out[:max_output]
    except subprocess.TimeoutExpired:
        return "[Timeout]"
    except FileNotFoundError:
        return f"[Error: {argv[0]} not found]"
    except Exception as exc:
        return f"[Error: {exc}]"


def head_lines(text: str, count: int) -> str:
    return "\n".join(text.splitlines()[:count])


def grep_lines(text: str, pattern: str, *, ignore_case: bool = True) -> str:
    flags = re.IGNORECASE if ignore_case else 0
    rx = re.compile(pattern, flags)
    return "\n".join(line for line in text.splitlines() if rx.search(line))
