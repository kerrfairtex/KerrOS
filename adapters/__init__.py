"""Adapters package."""

from importlib import import_module
from threading import Lock

__all__ = ["llm"]

_IMPORT_LOCK = Lock()


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    with _IMPORT_LOCK:
        module = globals().get(name)
        if module is None:
            module = import_module(f".{name}", __name__)
            globals()[name] = module
        return module
