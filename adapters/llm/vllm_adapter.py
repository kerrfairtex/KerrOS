"""
adapters/llm/vllm_adapter.py
==============================
LLMPort adapter for vLLM (OpenAI-compatible /v1 API).
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from adapters.llm.openai_compat import OpenAICompatClient, endpoint_from_env


class VLLMAdapter:
    """LLMPort implementation for self-hosted vLLM."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        base = endpoint or endpoint_from_env(
            "VLLM_ENDPOINT",
            "http://localhost:8000/v1",
        )
        self.model = model or os.getenv("VLLM_MODEL", "meta-llama/Llama-3.2-3B-Instruct")
        self.client = OpenAICompatClient(
            base_url=base,
            model=self.model,
            api_key=api_key or os.getenv("VLLM_API_KEY", ""),
            provider_name="vllm",
        )
        self.last_api = "vllm"

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
