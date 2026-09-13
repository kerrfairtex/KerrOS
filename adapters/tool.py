"""
adapters/tool.py
================
Shim: proposed future path for tool adapter namespace.
Current implementation: adapters/tools/claw_adapter.py and router_adapter.py.
"""

from adapters.tools.claw_adapter import ClawAdapter
from adapters.tools.router_adapter import RouterAdapter

__all__ = [
    "ClawAdapter",
    "RouterAdapter",
]
