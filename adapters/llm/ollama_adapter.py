"""
adapters/llm/ollama_adapter.py
================================
LLMPort adapter for Ollama (OpenAI-compatible /v1 API).
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from adapters.llm.openai_compat import OpenAICompatClient, endpoint_from_env


class OllamaAdapter:
    """LLMPort implementation for local Ollama."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model: str | None = None,
    ) -> None:
        base = endpoint or endpoint_from_env(
            "OLLAMA_ENDPOINT",
            "http://localhost:11434/v1",
        )
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2")
        self.client = OpenAICompatClient(
            base_url=base,
            model=self.model,
            provider_name="ollama",
        )
        self.last_api = "ollama"

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        return self.client.complete(
            prompt,
            system=system,
            history=history,
            max_tokens=max_tokens,
            **kwargs,
        )

    def status(self) -> dict[str, Any]:
        return self.client.status()

    def last_api_used(self) -> str | None:
        return self.last_api
