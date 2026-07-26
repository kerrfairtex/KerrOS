"""Adapters package."""

from importlib import import_module
from threading import RLock

__all__ = ["llm"]

_IMPORT_LOCK = RLock()


def __getattr__(name):
    """Lazily import adapter subpackages with a lock for safe concurrent access."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    with _IMPORT_LOCK:
        module = globals().get(name)
        if module is None:
            module = import_module(f".{name}", __name__)
            globals()[name] = module
        return module
