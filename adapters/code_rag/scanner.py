"""
Repository scanner (ADR-107 Soft).

- .gitignore-aware filtering (best-effort pathspec / fnmatch)
- Binary / vendor / build-artifact exclusion
- Incremental diff via mtime + content sha256
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".eggs",
    "eggs",
    "vendor",
    "third_party",
    "third-party",
    "data",
    "models",
    ".cursor",
}

_SKIP_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
}

_BINARY_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".whl",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".a",
    ".wasm",
    ".gguf",
    ".safetensors",
    ".pt",
    ".onnx",
}


def _load_gitignore(root: Path) -> list[str]:
    patterns: list[str] = []
    gi = root / ".gitignore"
    if not gi.is_file():
        return patterns
    try:
        for line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("!"):
                continue
            patterns.append(s)
    except Exception:
        pass
    return patterns


def _ignored(rel: str, patterns: list[str]) -> bool:
    """Minimal gitignore match (glob-ish); not a full git implementation."""
    name = Path(rel).name
    parts = rel.replace("\\", "/").split("/")
    for pat in patterns:
        p = pat.replace("\\", "/").lstrip("/")
        if p.endswith("/**"):
            p = p[:-3]
        # directory patterns: foo/ or foo
        dir_pat = p.endswith("/")
        base = p.rstrip("/")
        if dir_pat or ("/" not in base and "*" not in base):
            if base in parts or rel == base or rel.startswith(base + "/"):
                return True
        if p.startswith("*."):
            if name.endswith(p[1:]):
                return True
        elif p.endswith("/*"):
            prefix = p[:-2]
            if rel.startswith(prefix + "/") or any(part == prefix for part in parts):
                return True
        elif "/" in p:
            if rel == p or rel.startswith(p + "/"):
                return True
            if "*" in p:
                rx = "^" + re.escape(p).replace("\\*", ".*") + "$"
                if re.match(rx, rel) or re.match(rx, name):
                    return True
        elif "*" in p:
            rx = "^" + re.escape(p).replace("\\*", ".*") + "$"
            if re.match(rx, rel) or re.match(rx, name):
                return True
    return False


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def scan_repository(
    root: Path,
    *,
    previous: Optional[dict[str, Any]] = None,
    extensions: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Walk root and return {files: [{path, mtime, sha256, size, language_hint}],
    added, changed, removed, unchanged}.
    """
    root = root.resolve()
    patterns = _load_gitignore(root)
    prev_files = (previous or {}).get("files") or {}
    if isinstance(prev_files, list):
        prev_map = {f["path"]: f for f in prev_files if isinstance(f, dict) and f.get("path")}
    else:
        prev_map = dict(prev_files) if isinstance(prev_files, dict) else {}

    found: dict[str, dict[str, Any]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # prune skip dirs in-place
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _SKIP_DIRS and not d.endswith(".egg-info")
        ]
        rel_dir = str(Path(dirpath).relative_to(root)).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        if rel_dir and _ignored(rel_dir, patterns):
            dirnames[:] = []
            continue
        for name in filenames:
            if name in _SKIP_FILES or name.startswith("."):
                continue
            path = Path(dirpath) / name
            rel = str(path.relative_to(root)).replace("\\", "/")
            if _ignored(rel, patterns):
                continue
            suf = path.suffix.lower()
            if suf in _BINARY_EXT:
                continue
            if extensions is not None and suf and suf not in extensions:
                # still allow extensionless shebang scripts later via language detect
                if suf:
                    continue
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_size > 1_500_000:  # skip huge files
                continue
            # skip likely binary by NUL sniff
            try:
                with path.open("rb") as f:
                    sample = f.read(1024)
                if b"\x00" in sample:
                    continue
            except OSError:
                continue
            sha = file_sha(path)
            found[rel] = {
                "path": rel,
                "mtime": st.st_mtime,
                "size": st.st_size,
                "sha256": sha,
            }

    added, changed, unchanged = [], [], []
    for rel, meta in found.items():
        old = prev_map.get(rel)
        if not old:
            added.append(rel)
        elif old.get("sha256") != meta["sha256"]:
            changed.append(rel)
        else:
            unchanged.append(rel)
    removed = [p for p in prev_map if p not in found]

    return {
        "root": str(root),
        "files": found,
        "added": sorted(added),
        "changed": sorted(changed),
        "removed": sorted(removed),
        "unchanged": sorted(unchanged),
        "gitignore_patterns": len(patterns),
    }
