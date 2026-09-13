"""
tools/base.py
=============
Shim: proposed future abstract tool base.
Current implementations are in tools/registry.py and wrapped_tools/.
"""

from tools.registry import ToolDefinition

__all__ = ["ToolDefinition"]
