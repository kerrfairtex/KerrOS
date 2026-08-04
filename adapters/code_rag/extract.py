"""
Knowledge extraction (ADR-107 Soft).

Semantic chunks at function/class level + symbol/graph edges.
Fake regex when tree-sitter unavailable; Soft AST hook when present.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from adapters.code_rag.languages import detect_language, is_code_language

try:
    import tree_sitter  # noqa: F401

    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

# Indent groups use [ \t]* only — \s* would swallow the preceding newline under re.M.
_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "python": [
        ("class", re.compile(r"^(?P<indent>[ \t]*)class\s+(?P<name>\w+).*?:", re.M)),
        ("function", re.compile(r"^(?P<indent>[ \t]*)(?:async\s+)?def\s+(?P<name>\w+)\s*\(", re.M)),
    ],
    "javascript": [
        ("class", re.compile(r"^(?P<indent>[ \t]*)(?:export\s+)?class\s+(?P<name>\w+)", re.M)),
        (
            "function",
            re.compile(
                r"^(?P<indent>[ \t]*)(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*\(",
                re.M,
            ),
        ),
        (
            "function",
            re.compile(
                r"^(?P<indent>[ \t]*)(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?:async\s*)?\(",
                re.M,
            ),
        ),
    ],
    "typescript": [
        ("class", re.compile(r"^(?P<indent>[ \t]*)(?:export\s+)?class\s+(?P<name>\w+)", re.M)),
        (
            "function",
            re.compile(
                r"^(?P<indent>[ \t]*)(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*\(",
                re.M,
            ),
        ),
    ],
    "go": [
        ("function", re.compile(r"^(?P<indent>[ \t]*)func\s+(?:\([^)]*\)\s*)?(?P<name>\w+)\s*\(", re.M)),
        ("type", re.compile(r"^(?P<indent>[ \t]*)type\s+(?P<name>\w+)\s+struct", re.M)),
    ],
    "rust": [
        ("function", re.compile(r"^(?P<indent>[ \t]*)(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>\w+)", re.M)),
        ("struct", re.compile(r"^(?P<indent>[ \t]*)(?:pub\s+)?struct\s+(?P<name>\w+)", re.M)),
    ],
    "java": [
        ("class", re.compile(r"^(?P<indent>[ \t]*)(?:public\s+|private\s+)?class\s+(?P<name>\w+)", re.M)),
        (
            "function",
            re.compile(
                r"^(?P<indent>[ \t]*)(?:public|private|protected)?\s*(?:static\s+)?[\w<>\[\]]+\s+(?P<name>\w+)\s*\(",
                re.M,
            ),
        ),
    ],
}

_IMPORT_RE = {
    "python": re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M),
    "javascript": re.compile(
        r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))""",
        re.M,
    ),
    "typescript": re.compile(r"""import\s+.*?from\s+['"]([^'"]+)['"]""", re.M),
    "go": re.compile(r'^\s*import\s+(?:\(\s*)?"([^"]+)"', re.M),
    "rust": re.compile(r"^\s*use\s+([\w:]+)", re.M),
}

_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")
_DOC_RE = {
    "python": re.compile(r'^\s*(?:"""|\'\'\')([\s\S]*?)(?:"""|\'\'\')', re.M),
}


def _chunk_id(path: str, name: str, start: int) -> str:
    raw = f"{path}:{name}:{start}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _slice_block(lines: list[str], start_idx: int, indent: str) -> tuple[str, int, int]:
    """Take lines from start_idx until dedent at same/less indent (Soft)."""
    body = [lines[start_idx]]
    end = start_idx
    base_indent = len(indent)
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            body.append(line)
            end = i
            continue
        cur = len(line) - len(line.lstrip(" \t"))
        if cur <= base_indent and line.lstrip():
            break
        body.append(line)
        end = i
    text = "\n".join(body)
    return text, start_idx + 1, end + 1  # 1-based lines


def extract_file(path: str, text: str) -> dict[str, Any]:
    lang = detect_language(path, text)
    lines = text.splitlines()
    chunks: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # imports → graph edges
    ire = _IMPORT_RE.get(lang)
    if ire:
        for m in ire.finditer(text):
            target = next((g for g in m.groups() if g), None)
            if target:
                edges.append(
                    {
                        "src": path,
                        "dst": target,
                        "rel": "imports",
                        "line": text[: m.start()].count("\n") + 1,
                    }
                )

    patterns = _PATTERNS.get(lang) or []
    if is_code_language(lang) and patterns:
        for kind, rx in patterns:
            for m in rx.finditer(text):
                name = m.group("name")
                indent = m.groupdict().get("indent") or ""
                start_idx = text[: m.start()].count("\n")
                body, line_start, line_end = _slice_block(lines, start_idx, indent)
                # docstring Soft
                doc = ""
                if lang == "python":
                    dm = _DOC_RE["python"].search(body)
                    if dm:
                        doc = (dm.group(1) or "").strip()[:400]
                cid = _chunk_id(path, name, line_start)
                chunk = {
                    "id": cid,
                    "path": path,
                    "language": lang,
                    "kind": kind,
                    "name": name,
                    "line_start": line_start,
                    "line_end": line_end,
                    "text": body[:8000],
                    "docstring": doc,
                    "citation": f"{path}:{line_start}-{line_end}",
                }
                chunks.append(chunk)
                symbols.append(
                    {
                        "name": name,
                        "kind": kind,
                        "path": path,
                        "line": line_start,
                        "chunk_id": cid,
                        "language": lang,
                    }
                )
                # Soft call edges from body
                for cm in _CALL_RE.finditer(body):
                    callee = cm.group(1)
                    if callee == name or callee in ("if", "for", "while", "switch", "return"):
                        continue
                    edges.append(
                        {
                            "src": name,
                            "dst": callee,
                            "rel": "calls",
                            "path": path,
                            "chunk_id": cid,
                        }
                    )
    else:
        # Fallback: fixed-ish semantic-ish chunk for docs / unsupported langs
        if text.strip():
            cid = _chunk_id(path, Pathish(path), 1)
            chunks.append(
                {
                    "id": cid,
                    "path": path,
                    "language": lang,
                    "kind": "file",
                    "name": path.rsplit("/", 1)[-1],
                    "line_start": 1,
                    "line_end": max(1, len(lines)),
                    "text": text[:6000],
                    "docstring": "",
                    "citation": f"{path}:1-{max(1, len(lines))}",
                }
            )

    # module-level summary Soft
    complexity = len(symbols) + text.count("\n") // 40
    return {
        "path": path,
        "language": lang,
        "backend": "tree_sitter" if HAS_TREE_SITTER else "fake",
        "chunks": chunks,
        "symbols": symbols,
        "edges": edges[:500],
        "metadata": {
            "path": path,
            "language": lang,
            "symbol_count": len(symbols),
            "chunk_count": len(chunks),
            "complexity": complexity,
            "lines": len(lines),
        },
    }


def Pathish(path: str) -> str:
    return path.rsplit("/", 1)[-1]
