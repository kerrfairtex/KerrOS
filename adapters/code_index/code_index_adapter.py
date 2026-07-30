"""
adapters/code_index/code_index_adapter.py
=========================================
Soft workspace code index (Phase C / ADR-052).

Default-off unless offline profile ``coding`` is enabled or
``KERROS_CODE_INDEX=1``. Fake regex symbol extraction when tree-sitter
is missing; soft tree-sitter when installed. Content search prefers
``rg`` (ripgrep), falls back to a Python walk.

Index lives under ``data/code_index/`` — never OmniRoute / RAG paths.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional

from kernel.flags import is_true

try:
    import tree_sitter  # noqa: F401

    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".rb",
    ".php",
    ".cs",
    ".kt",
    ".swift",
    ".scala",
    ".sh",
}

# Fake regex extractors: (kind, pattern with one capture group for name)
_FAKE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("class", re.compile(r"^\s*class\s+(\w+)", re.M)),
    ("function", re.compile(r"^\s*def\s+(\w+)\s*\(", re.M)),
    ("function", re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(", re.M)),
    ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", re.M)),
    ("function", re.compile(r"^\s*fn\s+(\w+)\s*[<(]", re.M)),
    ("function", re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", re.M)),
    ("function", re.compile(r"^\s*(?:pub\s+)?fn\s+(\w+)", re.M)),
]

_SKIP_DIRS = {
    ".git",
    ".hg",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "data",
    "models",
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def ripgrep_available() -> bool:
    return bool(shutil.which("rg"))


def is_code_index_enabled(cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or {}
    env = os.getenv("KERROS_CODE_INDEX")
    if env is not None and str(env).strip() != "":
        return is_true(env)
    if "code_index_enabled" in data:
        return is_true(data.get("code_index_enabled"))
    try:
        from adapters.llm.offline_profile import (
            is_offline_profile_active,
            load_offline_profile,
        )

        if not is_offline_profile_active(data):
            return False
        profile = load_offline_profile(cfg=data)
        coding = profile.get("coding") if isinstance(profile, dict) else None
        if not isinstance(coding, dict):
            return False
        if coding.get("enabled") is False:
            return False
        # Opt in when profile asks for ripgrep and/or tree_sitter.
        return bool(coding.get("ripgrep") or coding.get("tree_sitter") or coding.get("enabled"))
    except Exception:
        return False


def resolve_code_index_path(
    cfg: dict[str, Any] | None = None,
    *,
    base: Optional[Path] = None,
) -> Path:
    data = cfg or {}
    raw = (
        os.getenv("KERROS_CODE_INDEX_PATH")
        or data.get("code_index_path")
        or "data/code_index/index.json"
    )
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        root = base
        if root is None:
            try:
                from kernel.config import load_config

                root = load_config().base
            except Exception:
                root = Path.home() / "offline_ai"
        path = Path(root) / path
    from rag.path_guard import assert_kerros_memory_path

    assert_kerros_memory_path(path, label="code_index_path")
    return path


def probe_code_index(config: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        from kernel.config import load_config

        cfg = dict(config or load_config().values)
    except Exception:
        cfg = dict(config or {})
    enabled = is_code_index_enabled(cfg)
    path = resolve_code_index_path(cfg)
    return {
        "component": "code_index",
        "enabled": enabled,
        "available": enabled,
        "path": str(path),
        "has_tree_sitter": HAS_TREE_SITTER,
        "has_ripgrep": ripgrep_available(),
        "status": "ok" if enabled else "disabled",
    }


def _extract_fake_symbols(text: str, rel: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kind, pattern in _FAKE_PATTERNS:
        for m in pattern.finditer(text):
            name = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            out.append(
                {
                    "name": name,
                    "kind": kind,
                    "path": rel,
                    "line": line,
                    "backend": "fake",
                }
            )
    return out


class CodeIndexAdapter:
    """Soft CodeIndexPort implementation."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        workspace: Optional[Path] = None,
        base: Optional[Path] = None,
    ) -> None:
        cfg = dict(config or {})
        try:
            if not cfg:
                from kernel.config import load_config

                cfg = dict(load_config().values)
        except Exception:
            pass
        self._cfg = cfg
        self.enabled = is_code_index_enabled(cfg)
        self.index_path = resolve_code_index_path(cfg, base=base)
        if workspace is not None:
            self.workspace = Path(workspace).resolve()
        else:
            from tools.claw_tools import get_workspace

            self.workspace = get_workspace()
        self.backend = "tree_sitter" if HAS_TREE_SITTER else "fake"
        self.last_error = ""
        self._symbols: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if self.index_path.is_file():
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                self._symbols = list(data.get("symbols") or [])
                self.last_error = ""
            except Exception as exc:
                self._symbols = []
                self.last_error = str(exc)

    def _persist(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "backend": self.backend,
            "workspace": str(self.workspace),
            "symbols": self._symbols,
            "count": len(self._symbols),
        }
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _iter_files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix.lower() in CODE_EXTENSIONS:
                    files.append(path)
        return files

    def build(self, root: str | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {
                "ok": False,
                "skipped": True,
                "error": "code index disabled",
                "enabled": False,
            }
        base = self.workspace
        if root:
            candidate = (self.workspace / root).resolve()
            try:
                candidate.relative_to(self.workspace)
            except ValueError:
                return {"ok": False, "error": "root escapes workspace"}
            base = candidate
        symbols: list[dict[str, Any]] = []
        files = self._iter_files(base)
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(self.workspace)).replace("\\", "/")
            # Soft tree-sitter path reserved — Fake regex is the CI default.
            if HAS_TREE_SITTER:
                # Without language grammars wired, still use Fake extractors;
                # mark backend so operators know tree-sitter is importable.
                extracted = _extract_fake_symbols(text, rel)
                for item in extracted:
                    item["backend"] = "tree_sitter+fake"
                symbols.extend(extracted)
            else:
                symbols.extend(_extract_fake_symbols(text, rel))
        with self._lock:
            self._symbols = symbols
            self._persist()
            self.last_error = ""
        return {
            "ok": True,
            "backend": self.backend,
            "files": len(files),
            "symbols": len(symbols),
            "path": str(self.index_path),
            "has_tree_sitter": HAS_TREE_SITTER,
            "has_ripgrep": ripgrep_available(),
        }

    def search_symbols(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        q = (query or "").strip().lower()
        if not q:
            return []
        with self._lock:
            if not self._symbols:
                self._load()
            hits = [s for s in self._symbols if q in str(s.get("name", "")).lower()]
        return hits[: max(1, int(top_k))]

    def search_content(self, pattern: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        pat = (pattern or "").strip()
        if not pat:
            return []
        limit = max(1, int(top_k))
        if ripgrep_available():
            try:
                proc = subprocess.run(
                    [
                        "rg",
                        "--json",
                        "-m",
                        str(limit),
                        "--glob",
                        "!data/**",
                        "--glob",
                        "!models/**",
                        "--glob",
                        "!.git/**",
                        pat,
                        str(self.workspace),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                hits: list[dict[str, Any]] = []
                for line in (proc.stdout or "").splitlines():
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") != "match":
                        continue
                    data = obj.get("data") or {}
                    path = data.get("path", {}).get("text", "")
                    try:
                        rel = str(Path(path).resolve().relative_to(self.workspace))
                    except Exception:
                        rel = path
                    line_no = int((data.get("line_number") or 0))
                    text = (data.get("lines") or {}).get("text", "").rstrip("\n")
                    hits.append(
                        {
                            "path": rel.replace("\\", "/"),
                            "line": line_no,
                            "text": text[:240],
                            "backend": "ripgrep",
                        }
                    )
                    if len(hits) >= limit:
                        break
                return hits
            except Exception as exc:
                self.last_error = str(exc)

        # Python fallback walk
        hits = []
        try:
            regex = re.compile(pat)
        except re.error:
            regex = re.compile(re.escape(pat))
        for path in self._iter_files(self.workspace):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(self.workspace)).replace("\\", "/")
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    hits.append(
                        {
                            "path": rel,
                            "line": i,
                            "text": line[:240],
                            "backend": "python",
                        }
                    )
                    if len(hits) >= limit:
                        return hits
        return hits

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "path": str(self.index_path),
            "workspace": str(self.workspace),
            "symbols": len(self._symbols),
            "has_tree_sitter": HAS_TREE_SITTER,
            "has_ripgrep": ripgrep_available(),
            "last_error": self.last_error,
        }


def build_code_index(
    cfg: Optional[dict[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[CodeIndexAdapter]:
    resolved = dict(cfg or {})
    if not is_code_index_enabled(resolved):
        # Still construct when explicitly requested via empty cfg + env off → None
        adapter = CodeIndexAdapter(resolved, base=base)
        if not adapter.enabled:
            return None
        return adapter
    return CodeIndexAdapter(resolved, base=base)
