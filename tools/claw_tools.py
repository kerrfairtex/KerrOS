"""
tools/claw_tools.py
====================
OpenClaw-style filesystem and execution tools for KerrOS agents.

Provides deterministic, schema-driven operations:
  - read      — read file contents (with offset/limit)
  - write     — create or overwrite files
  - edit      — targeted search/replace within a file
  - list      — list directory entries
  - exec      — run shell commands in the workspace
  - apply_patch — apply unified-diff patches

All filesystem paths are resolved under the workspace root and cannot
escape it. Shell commands are gated by config.json safe_commands.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.shell_utils import ShellCommandError, run_argv, split_command

DEFAULT_WORKSPACE = Path(__file__).resolve().parent.parent
WORKSPACE = Path(
    os.environ.get("KERROS_WORKSPACE", os.environ.get("KERROS_PROJECT_ROOT", str(DEFAULT_WORKSPACE)))
).expanduser().resolve()

MAX_READ_BYTES = 512_000
MAX_OUTPUT_CHARS = 50_000
DEFAULT_EXEC_TIMEOUT = 60


class ClawToolError(Exception):
    pass


@dataclass
class ToolResult:
    ok: bool
    tool: str
    output: str = ""
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "output": self.output,
            "error": self.error,
            "data": self.data,
        }


def get_workspace() -> Path:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return WORKSPACE


def _resolve_path(path: str) -> Path:
    if not path or not str(path).strip():
        raise ClawToolError("path is required")

    raw = str(path).strip()
    root = get_workspace()

    if os.path.isabs(raw):
        target = Path(raw).expanduser().resolve()
    else:
        target = (root / raw).resolve()

    try:
        target.relative_to(root)
    except ValueError:
        raise ClawToolError(f"path escapes workspace: {path}")

    return target


def _load_safe_commands() -> set[str]:
    try:
        from kernel.config import load_config
        cfg = load_config().values
        return {str(c).strip() for c in cfg.get("safe_commands", []) if str(c).strip()}
    except Exception:
        pass
    config_path = get_workspace() / "config.json"
    if not config_path.exists():
        config_path = DEFAULT_WORKSPACE / "config.json"
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        return {str(c).strip() for c in cfg.get("safe_commands", []) if str(c).strip()}
    except Exception:
        return set()


def _check_exec_allowed(command: str) -> None:
    cmd = command.strip()
    if not cmd:
        raise ClawToolError("command is required")

    base = cmd.split()[0]
    if base in {"sudo", "su", "doas"}:
        raise ClawToolError(f"blocked privileged command: {base}")

    safe = _load_safe_commands()
    if safe and base not in safe:
        raise ClawToolError(
            f"command '{base}' not in safe_commands — add it to config.json or use a permitted command"
        )


def read(
    path: str,
    offset: int = 1,
    limit: int | None = None,
) -> ToolResult:
    """Read a file under the workspace."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return ToolResult(False, "read", error=f"not found: {path}")
        if target.is_dir():
            return ToolResult(False, "read", error=f"is a directory: {path}")

        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            return ToolResult(
                False,
                "read",
                error=f"file too large ({size} bytes, max {MAX_READ_BYTES})",
            )

        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)

        start = max(1, int(offset)) - 1
        if limit is not None:
            end = start + max(1, int(limit))
            selected = lines[start:end]
        else:
            selected = lines[start:]

        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i:6d}|{line.rstrip()}")

        output = "\n".join(numbered)
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... [truncated]"

        return ToolResult(
            True,
            "read",
            output=output,
            data={"path": str(target), "total_lines": len(lines)},
        )
    except ClawToolError as e:
        return ToolResult(False, "read", error=str(e))
    except Exception as e:
        return ToolResult(False, "read", error=str(e))


def write(path: str, content: str) -> ToolResult:
    """Create or overwrite a file under the workspace."""
    try:
        target = _resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if content is not None else "", encoding="utf-8")
        return ToolResult(
            True,
            "write",
            output=f"wrote {len(content or '')} bytes to {path}",
            data={"path": str(target), "bytes": len((content or "").encode("utf-8"))},
        )
    except ClawToolError as e:
        return ToolResult(False, "write", error=str(e))
    except Exception as e:
        return ToolResult(False, "write", error=str(e))


def edit(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> ToolResult:
    """Replace old_string with new_string in a file."""
    try:
        if not old_string:
            return ToolResult(False, "edit", error="old_string is required")

        target = _resolve_path(path)
        if not target.exists():
            return ToolResult(False, "edit", error=f"not found: {path}")
        if target.is_dir():
            return ToolResult(False, "edit", error=f"is a directory: {path}")

        text = target.read_text(encoding="utf-8")
        count = text.count(old_string)
        if count == 0:
            return ToolResult(False, "edit", error="old_string not found in file")
        if count > 1 and not replace_all:
            return ToolResult(
                False,
                "edit",
                error=f"old_string appears {count} times — set replace_all=true or use a more specific match",
            )

        updated = text.replace(old_string, new_string, count if replace_all else 1)
        target.write_text(updated, encoding="utf-8")
        replacements = count if replace_all else 1
        return ToolResult(
            True,
            "edit",
            output=f"replaced {replacements} occurrence(s) in {path}",
            data={"path": str(target), "replacements": replacements},
        )
    except ClawToolError as e:
        return ToolResult(False, "edit", error=str(e))
    except Exception as e:
        return ToolResult(False, "edit", error=str(e))


def list_dir(path: str = ".", recursive: bool = False) -> ToolResult:
    """List files and directories under the workspace."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return ToolResult(False, "list", error=f"not found: {path}")
        if target.is_file():
            rel = target.relative_to(get_workspace())
            return ToolResult(True, "list", output=str(rel), data={"entries": [str(rel)]})

        root = get_workspace()
        entries: list[str] = []

        if recursive:
            for p in sorted(target.rglob("*")):
                rel = p.relative_to(root)
                suffix = "/" if p.is_dir() else ""
                entries.append(f"{rel}{suffix}")
        else:
            for p in sorted(target.iterdir()):
                rel = p.relative_to(root)
                tag = "DIR " if p.is_dir() else "FILE"
                entries.append(f"[{tag}] {rel}{'/' if p.is_dir() else ''}")

        output = "\n".join(entries) if entries else "(empty)"
        return ToolResult(True, "list", output=output, data={"entries": entries})
    except ClawToolError as e:
        return ToolResult(False, "list", error=str(e))
    except Exception as e:
        return ToolResult(False, "list", error=str(e))


def exec_cmd(
    command: str,
    cwd: str | None = None,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> ToolResult:
    """Execute a shell command within the workspace."""
    try:
        _check_exec_allowed(command)
        workdir = _resolve_path(cwd or ".") if cwd else get_workspace()
        if not workdir.is_dir():
            return ToolResult(False, "exec", error=f"cwd is not a directory: {cwd or '.'}")

        run_env = os.environ.copy()
        if env:
            run_env.update({str(k): str(v) for k, v in env.items()})

        secs = DEFAULT_EXEC_TIMEOUT if timeout is None else max(1, int(timeout))
        try:
            argv = split_command(command)
        except ShellCommandError as exc:
            return ToolResult(False, "exec", error=str(exc))

        proc = subprocess.run(
            argv,
            shell=False,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=secs,
            env=run_env,
        )

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        combined = stdout
        if stderr:
            combined = f"{stdout}\n{stderr}".strip() if stdout else stderr
        if len(combined) > MAX_OUTPUT_CHARS:
            combined = combined[:MAX_OUTPUT_CHARS] + "\n... [truncated]"

        ok = proc.returncode == 0
        return ToolResult(
            ok,
            "exec",
            output=combined or "(no output)",
            error="" if ok else f"exit code {proc.returncode}",
            data={
                "exit_code": proc.returncode,
                "stdout": stdout[:MAX_OUTPUT_CHARS],
                "stderr": stderr[:MAX_OUTPUT_CHARS],
                "cwd": str(workdir),
            },
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, "exec", error=f"timeout after {timeout or DEFAULT_EXEC_TIMEOUT}s")
    except ClawToolError as e:
        return ToolResult(False, "exec", error=str(e))
    except Exception as e:
        return ToolResult(False, "exec", error=str(e))


def apply_patch(patch: str, workspace_only: bool = True) -> ToolResult:
    """
    Apply a unified diff patch. Supports file add/modify hunks.
    When workspace_only is True (default), all paths must stay in workspace.
    """
    try:
        if not patch or not patch.strip():
            return ToolResult(False, "apply_patch", error="patch is required")

        files_changed: list[str] = []
        current_file: str | None = None
        original_lines: list[str] = []
        new_lines: list[str] = []
        in_hunk = False

        def _flush():
            nonlocal current_file, original_lines, new_lines, in_hunk
            if current_file is None:
                return
            target = _resolve_path(current_file) if workspace_only else Path(current_file).resolve()
            if workspace_only:
                try:
                    target.relative_to(get_workspace())
                except ValueError:
                    raise ClawToolError(f"patch path escapes workspace: {current_file}")

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("".join(new_lines), encoding="utf-8")
            files_changed.append(current_file)
            current_file = None
            original_lines = []
            new_lines = []
            in_hunk = False

        for line in patch.splitlines(keepends=True):
            if line.startswith("--- "):
                _flush()
                continue
            if line.startswith("+++ "):
                path_part = line[4:].strip()
                if path_part.startswith("b/"):
                    path_part = path_part[2:]
                current_file = path_part
                target = _resolve_path(current_file) if workspace_only else Path(current_file)
                if target.exists() and target.is_file():
                    original_lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
                    new_lines = original_lines.copy()
                else:
                    original_lines = []
                    new_lines = []
                continue
            if line.startswith("@@"):
                in_hunk = True
                continue
            if not in_hunk or current_file is None:
                continue

            if line.startswith(" "):
                new_lines.append(line[1:])
            elif line.startswith("+"):
                new_lines.append(line[1:])
            elif line.startswith("-"):
                pass
            elif line.startswith("\\"):
                pass

        _flush()

        if not files_changed:
            return ToolResult(False, "apply_patch", error="no files changed — invalid or empty patch")

        return ToolResult(
            True,
            "apply_patch",
            output=f"applied patch to {len(files_changed)} file(s)",
            data={"files": files_changed},
        )
    except ClawToolError as e:
        return ToolResult(False, "apply_patch", error=str(e))
    except Exception as e:
        return ToolResult(False, "apply_patch", error=str(e))


def remove(path: str) -> ToolResult:
    """Delete a file or directory under the workspace."""
    import shutil

    try:
        target = _resolve_path(path)
        if not target.exists():
            return ToolResult(False, "remove", error=f"not found: {path}")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return ToolResult(True, "remove", output=f"removed {path}")
    except ClawToolError as e:
        return ToolResult(False, "remove", error=str(e))
    except Exception as e:
        return ToolResult(False, "remove", error=str(e))
