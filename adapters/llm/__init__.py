"""
adapters/llm/__init__.py

LLM adapters — implementations of LLMPort wrapping various LLM backends.

Phase 1:
  - MultiAPIAdapter: Wraps core/multi_api.py (8-API fallback chain)

Phase 2+:
  - OfflineAdapter: Local llama.cpp / Ollama integration
  - TogetherAIAdapter: Together AI provider
  - MistralAdapter: Mistral provider
  - etc.

Each adapter is a drop-in replacement for any other; callers don't care
which backend is active, only that it conforms to LLMPort protocol.
"""

from adapters.llm.multi_api_adapter import MultiAPIAdapter

__all__ = ["MultiAPIAdapter"]
