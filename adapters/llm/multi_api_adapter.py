"""
adapters/llm/multi_api_adapter.py
==================================
LLMPort adapter wrapping core/multi_api.py's 8-API fallback chain.

PHASE 1: Zero behavioral change — pure wrapper over existing multi_api.py.
  - Task detection (coding, math, research, teaching, reasoning, chat)
  - Provider-specific routing chains (DeepSeek for coding, NVIDIA for research, etc.)
  - Retry logic and dead-API tracking
  - All internal to this adapter; not exposed via LLMPort interface.

PHASE 2+: Will be superseded by ExecutionPort-based adapter that reads chains
  from capability registry / config file instead of hard-coded if/elif branches.

ACCEPTANCE CRITERIA (Phase 1):
  ✓ Adapter output identical to calling multi_api.py.generate() directly
  ✓ All existing tests pass without modification
  ✓ At least one real call site migrated to prove end-to-end
"""

import sys
import os
from typing import Any, Optional, List

# Ensure core/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.multi_api import MultiAPIEngine
from ports.llm_port import LLMPort


class MultiAPIAdapter(LLMPort):
    """
    LLMPort implementation wrapping core/multi_api.py.
    
    Preserves all existing behavior: task-specific routing, fallback chains,
    retry logic, and dead-API tracking. Acts as a pure compatibility layer
    between LLMPort callers and the underlying multi_api.py engine.
    
    Usage:
        adapter = MultiAPIAdapter()
        result = adapter.complete("Write a Python function", system="You are helpful.")
        
        # Result will route to DeepSeek → NVIDIA → Groq for coding tasks,
        # exactly as multi_api.py.generate() does today.
    """

    def __init__(self):
        """Initialize the wrapped MultiAPIEngine."""
        self.engine = MultiAPIEngine()

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any
    ) -> str:
        """
        Generate a completion via multi_api.py's fallback chain.
        
        Delegates to MultiAPIEngine.generate() with zero modifications.
        
        Args:
            prompt: User message to complete.
            system: Optional system instruction.
            history: Optional prior conversation turns.
            max_tokens: Max tokens in response (per-provider capping handled by adapter).
            **kwargs: Ignored in Phase 1. Phase 2+ may use task_override, provider_hint.
        
        Returns:
            Completion text from whichever provider succeeded.
        
        Raises:
            RuntimeError: If all configured providers fail (after retries).
                          Falls back to offline mode message (placeholder for now).
        
        Implementation:
            - Passes {prompt, system, history, max_tokens} to engine.generate()
            - Engine detects task (coding, research, etc.) from prompt keywords
            - Engine tries task-specific chain, then powerhouse fallback
            - Dead-API tracking prevents cascade failures
            - Returns completion or error message
        """
        return self.engine.generate(
            user_message=prompt,
            system=system,
            history=history or [],
            max_tokens=max_tokens
        )

    def status(self) -> dict:
        """
        Return provider health status.
        
        Used for debugging / monitoring. Shows which providers are configured,
        which failed with auth errors, which had network issues, etc.
        
        Returns:
            Dict: {"groq": bool, "nvidia": bool, ...} indicating key presence.
                  Call engine.health to see detailed status per provider.
        """
        return self.engine.status()

    def last_api_used(self) -> Optional[str]:
        """Return the name of the last provider that succeeded."""
        return self.engine.last_api
