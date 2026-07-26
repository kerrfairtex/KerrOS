"""
ports/llm_port.py
=================
LLMPort — Stable interface for language model completion.

PHASE 1 (NOW):
  This is a compatibility wrapper over core/multi_api.py's 8-API fallback chain.
  Zero behavioral change: all existing task-specific routing, retry logic, and
  dead-API tracking remain internal to the adapter.

PHASE 2+ (FUTURE):
  LLMPort will be superseded by ExecutionPort + CapabilityRegistry, which
  decouples provider selection from execution semantics. This allows:
  - Config-driven provider re-prioritization (no code edits)
  - Dynamic provider registration (add Together AI, Mistral, etc. at runtime)
  - Offline mode integration (local llama.cpp/Ollama as equal provider)

DESIGN PRINCIPLE:
  No provider should be hard-coded into the kernel. This Port abstracts away
  the choice of LLM backend, enabling swaps without touching router.py or
  any agent code.

ACCEPTANCE CRITERIA:
  - Adapter passes through to multi_api.py unchanged
  - Existing fallback behavior verified identical via existing tests
  - At least one real call site migrated to prove end-to-end
"""

from typing import Optional, List, Protocol, Any


class LLMPort(Protocol):
    """
    Protocol for language model completion requests.
    
    Implementations wrap concrete LLM backends (Groq, Gemini, DeepSeek, etc.)
    behind a unified interface. Task-specific routing (coding vs. research vs.
    chat) and fallback chain logic remain the adapter's responsibility during
    Phase 1.
    
    This is intentionally minimal to reduce coupling between kernel dispatch
    and provider selection strategy.
    """

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any
    ) -> str:
        """
        Generate a completion for the given prompt.
        
        Args:
            prompt: User message / query to complete.
            system: Optional system message / instruction.
            history: Optional list of prior turns, each as {"role": "user"|"assistant", "content": "..."}
            max_tokens: Maximum tokens in response. Adapter adjusts per provider limits.
            **kwargs: Future extension point (e.g., provider_hint, task_override).
                      Phase 1 ignores these; Phase 2+ ExecutionPort will consume them.
        
        Returns:
            Completion text from the underlying model.
        
        Raises:
            RuntimeError: If all configured providers fail (after retries).
        
        Implementation note (Phase 1):
          - Adapter routes {prompt, system, history} to multi_api.py.generate()
          - Task detection happens inside adapter (not caller's responsibility)
          - Fallback chain (DeepSeek → NVIDIA → Groq for coding, etc.) is internal
          - Dead-API tracking prevents cascade failures
        
        Implementation note (Phase 2+):
          - Caller may pass provider_hint or task_override in kwargs
          - Adapter consults capability registry instead of hard-coded chains
          - Offline mode (local llama.cpp) treated as just another provider
        """
        ...

    def last_api_used(self) -> Optional[str]:
        """Return the last provider that satisfied a completion request."""
        ...
