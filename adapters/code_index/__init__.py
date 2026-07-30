"""adapters.code_index — Phase C soft coding index."""

from adapters.code_index.code_index_adapter import (
    CodeIndexAdapter,
    build_code_index,
    is_code_index_enabled,
    probe_code_index,
    ripgrep_available,
)

__all__ = [
    "CodeIndexAdapter",
    "build_code_index",
    "is_code_index_enabled",
    "probe_code_index",
    "ripgrep_available",
]
