"""Language detection & routing heuristics (ADR-107 Soft)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

EXT_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".md": "markdown",
    ".rst": "rst",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".sql": "sql",
}

SHEBANG = {
    "python": "python",
    "python3": "python",
    "node": "javascript",
    "bash": "shell",
    "sh": "shell",
    "ruby": "ruby",
}

CODE_EXTS = {e for e, lang in EXT_LANG.items() if lang not in ("markdown", "rst", "toml", "yaml", "json")}


def detect_language(path: str, text: str = "") -> str:
    suf = Path(path).suffix.lower()
    if suf in EXT_LANG:
        return EXT_LANG[suf]
    if text.startswith("#!"):
        first = text.splitlines()[0].lower()
        for key, lang in SHEBANG.items():
            if key in first:
                return lang
    # content heuristics
    head = (text or "")[:400]
    if "def " in head and "import " in head:
        return "python"
    if "function " in head or "const " in head:
        return "javascript"
    if "package " in head and "func " in head:
        return "go"
    if "fn " in head and "let " in head:
        return "rust"
    return "unknown"


def is_code_language(lang: str) -> bool:
    return lang in {
        "python",
        "javascript",
        "typescript",
        "go",
        "rust",
        "java",
        "c",
        "cpp",
        "ruby",
        "php",
        "csharp",
        "kotlin",
        "swift",
        "scala",
        "shell",
        "sql",
    }
