"""
core/completion.py
==================
Shim: proposed future facade for completion/runtime modules.
Current implementations remain in place:
- core/complete.py
- core/unified_completion.py
- core/completion_*.py
"""

from core.complete import complete
from core.unified_completion import unified_complete

__all__ = ["complete", "unified_complete"]
