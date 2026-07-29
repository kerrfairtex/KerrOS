"""
rag/path_guard.py
=================
Refuse KerrOS RAG / knowledge paths that point at OmniRoute storage (P5).

OmniRoute FTS5+vector memory and KerrOS RAG are different jobs — never merge.
See docs/MEMORY_SEPARATION.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

# Path fragments that indicate OmniRoute (or its deploy kit) storage.
OMNIROUTE_PATH_MARKERS: tuple[str, ...] = (
    "deploy/omniroute",
    "kerros-omniroute-data",
    "/app/data",  # OmniRoute container DATA_DIR default
)

KERROS_QDRANT_COLLECTION_DEFAULT = "kerros_memory"


class MemorySeparationError(ValueError):
    """Raised when a KerrOS memory path collides with OmniRoute storage."""


def looks_like_omniroute_path(path: str | Path) -> bool:
    text = str(path).replace("\\", "/").lower()
    return any(marker in text for marker in OMNIROUTE_PATH_MARKERS)


def assert_kerros_memory_path(
    path: str | Path,
    *,
    label: str = "path",
) -> str:
    """Return resolved path string or raise MemorySeparationError."""
    raw = str(path)
    if looks_like_omniroute_path(raw):
        raise MemorySeparationError(
            f"{label} collides with OmniRoute storage ({raw}). "
            "Keep OmniRoute FTS/vector memory separate from KerrOS RAG "
            "(docs/MEMORY_SEPARATION.md)."
        )
    return raw


def assert_kerros_paths(paths: Iterable[tuple[str, str | Path]]) -> None:
    for label, path in paths:
        assert_kerros_memory_path(path, label=label)


def assert_qdrant_collection(name: Optional[str]) -> str:
    """Allow KerrOS collections; reject empty / OmniRoute-looking names."""
    collection = (name or KERROS_QDRANT_COLLECTION_DEFAULT).strip()
    lowered = collection.lower()
    if not collection:
        raise MemorySeparationError("qdrant_collection must not be empty")
    # OmniRoute may use product-specific collection names; keep KerrOS distinct.
    if "omniroute" in lowered and lowered != KERROS_QDRANT_COLLECTION_DEFAULT:
        raise MemorySeparationError(
            f"qdrant_collection '{collection}' looks OmniRoute-owned; "
            f"use '{KERROS_QDRANT_COLLECTION_DEFAULT}' for KerrOS "
            "(docs/MEMORY_SEPARATION.md)."
        )
    return collection
