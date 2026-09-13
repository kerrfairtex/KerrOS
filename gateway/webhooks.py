"""
gateway/webhooks.py
===================
Shim: proposed future path for webhook gateway.
Current implementation: gateway/webhook.py
"""

from gateway.webhook import app as webhooks

__all__ = ["webhooks"]
