"""
gateway/provider.py
===================
Shim: proposed future namespace for gateway providers/channels.
Current implementations remain under gateway/channels/.
"""

from gateway.channels import telegram, discord, signal, whatsapp, routing, registry, slash

__all__ = [
    "telegram",
    "discord",
    "signal",
    "whatsapp",
    "routing",
    "registry",
    "slash",
]
