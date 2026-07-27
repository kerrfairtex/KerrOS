"""
adapters/llm/litellm_adapter.py
================================
LLMPort adapter for a local LiteLLM proxy server.

LiteLLM (https://github.com/BerriAI/litellm) exposes an OpenAI-compatible
/v1 endpoint that can route to 100+ providers (Anthropic, Gemini, Cohere,
Bedrock, Azure, etc.).  Spin it up with:

    litellm --model gpt-4o  # or any supported model string
    # default listen address: http://localhost:4000

Set LITELLM_ENDPOINT to override the default address.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from adapters.llm.openai_compat import OpenAICompatClient, endpoint_from_env


class LiteLLMAdapter:
    """LLMPort implementation for a self-hosted LiteLLM proxy."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        base = endpoint or endpoint_from_env(
            "LITELLM_ENDPOINT",
            "http://localhost:4000/v1",
        )
        self.model = model or os.getenv("LITELLM_MODEL", "gpt-4o-mini")
        self.client = OpenAICompatClient(
            base_url=base,
            model=self.model,
            api_key=api_key or os.getenv("LITELLM_API_KEY", ""),
            provider_name="litellm",
        )
        self.last_api = "litellm"

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

    def available(self) -> bool:
        return self.client.available()

    def last_api_used(self) -> str | None:
        return self.last_api
