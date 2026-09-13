"""
kernel/__init__.py
==================
Public facade for the bootstrap/config layer.

Preferred import style:
    from kernel import get_kernel, resolve
    from kernel import load_config
    from kernel import memory_query, memory_search_by_category
"""

from kernel.boot import get_kernel, resolve, shutdown, boot  # noqa: F401
from kernel.config import load_config  # noqa: F401
from kernel.access import (  # noqa: F401
    memory_query,
    memory_search_by_category,
    memory_search_multi_category,
    memory_search_exact_id,
)

__all__ = [
    "get_kernel",
    "resolve",
    "shutdown",
    "boot",
    "load_config",
    "memory_query",
    "memory_search_by_category",
    "memory_search_multi_category",
    "memory_search_exact_id",
]
