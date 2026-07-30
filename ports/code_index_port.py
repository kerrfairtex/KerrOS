"""
ports/code_index_port.py
========================
CodeIndexPort — workspace symbol / content search for the coding assistant.
"""

from __future__ import annotations

from typing import Any, Protocol


class CodeIndexPort(Protocol):
    def build(self, root: str | None = None) -> dict[str, Any]:
        """Rebuild the workspace code index."""
        ...

    def search_symbols(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        """Lookup symbols by name substring."""
        ...

    def search_content(self, pattern: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        """Search file contents (ripgrep when available)."""
        ...

    def status(self) -> dict[str, Any]:
        ...
