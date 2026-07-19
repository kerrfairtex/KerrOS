"""
tools/fs_tool.py
=================
Deterministic file/folder operations for KerrOS agents.

Why this exists: letting the LLM freehand bash for file creation is
unreliable (missing `mkdir -p`, tree-diagrams mistaken for scripts,
self-fix loops patching symptoms instead of causes). These functions
are called directly as tools instead — no shell generation involved.

Every path is resolved relative to PROJECT_ROOT and cannot escape it
(basic guardrail against '../../' traversal from a bad model output).
"""

import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("KERROS_PROJECT_ROOT", "~/offline_ai/generated_code")).expanduser()
PROJECT_ROOT.mkdir(parents=True, exist_ok=True)


class FsToolError(Exception):
    pass


def _resolve(rel_path: str) -> Path:
    """Resolve a path under PROJECT_ROOT, blocking traversal outside it."""
    target = (PROJECT_ROOT / rel_path).resolve()
    if PROJECT_ROOT.resolve() not in target.parents and target != PROJECT_ROOT.resolve():
        raise FsToolError(f"path escapes project root: {rel_path}")
    return target


def create_file(rel_path: str, content: str = "") -> str:
    """Create a file, making all parent directories first. Never fails on missing dirs."""
    target = _resolve(rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def read_file(rel_path: str) -> str:
    target = _resolve(rel_path)
    if not target.exists():
        raise FsToolError(f"not found: {rel_path}")
    return target.read_text(encoding="utf-8")


def write_file(rel_path: str, content: str, append: bool = False) -> str:
    """Write/overwrite a file. Creates parent dirs if missing."""
    target = _resolve(rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(target, mode, encoding="utf-8") as f:
        f.write(content)
    return str(target)


def remove(rel_path: str) -> str:
    """Delete a file or a directory (recursively)."""
    target = _resolve(rel_path)
    if not target.exists():
        raise FsToolError(f"not found: {rel_path}")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return f"removed {rel_path}"


def move(src_rel: str, dst_rel: str) -> str:
    src = _resolve(src_rel)
    dst = _resolve(dst_rel)
    if not src.exists():
        raise FsToolError(f"not found: {src_rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"moved {src_rel} -> {dst_rel}"


def scan(rel_path: str = ".") -> list[str]:
    """List all files/dirs under rel_path, relative to PROJECT_ROOT."""
    target = _resolve(rel_path)
    if not target.exists():
        raise FsToolError(f"not found: {rel_path}")
    if target.is_file():
        return [str(target.relative_to(PROJECT_ROOT))]
    results = []
    for p in sorted(target.rglob("*")):
        results.append(str(p.relative_to(PROJECT_ROOT)) + ("/" if p.is_dir() else ""))
    return results


def make_skeleton(rel_root: str, structure: dict) -> list[str]:
    """
    Create a nested file/folder skeleton in one call — the safe replacement
    for 'ask the model to write mkdir/touch bash and hope it's correct'.

    structure format (dict tree, files map to their string content):
        {
            "public": {"index.html": "<html></html>"},
            "src": {
                "App.js": "",
                "components": {},   # empty dict = empty folder
            },
            "README.md": "# project",
        }
    """
    created = []

    def _walk(node: dict, prefix: str):
        for name, value in node.items():
            path = f"{prefix}/{name}" if prefix else name
            if isinstance(value, dict):
                if not value:
                    target = _resolve(path)
                    target.mkdir(parents=True, exist_ok=True)
                    created.append(str(target) + "/")
                else:
                    _walk(value, path)
            else:
                created.append(create_file(path, value or ""))

    root = f"{rel_root}"
    _walk(structure, root)
    return created
