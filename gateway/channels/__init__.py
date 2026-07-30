"""
gateway/channels/__init__.py
============================
Pluggable messaging channel adapters (ADR-066).
"""

from gateway.channels.registry import get_adapter, list_channels, register_channel

__all__ = ["get_adapter", "list_channels", "register_channel"]
