"""
adapters/llm/omniroute_adapter.py
=================================
OmniRoute-compatible LLM adapter over a single OpenAI-compatible endpoint.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from adapters.llm.openai_compat import OpenAICompatClient
from kernel.flags import is_true
from kernel.config import load_config


class OmniRouteAdapter:
    """LLM adapter for a unified local OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        cfg = load_config().values
        enabled_cfg = cfg.get("use_omniroute", False)
        self._enabled = is_true(os.getenv("KERROS_USE_OMNIROUTE", enabled_cfg))
        self._base_url = (
            os.getenv("KERROS_OMNIROUTE_URL")
            or cfg.get("omniroute_url")
            or "http://127.0.0.1:20128/v1"
        )
        self._model = (
            os.getenv("KERROS_OMNIROUTE_MODEL")
            or cfg.get("omniroute_model")
            or "gpt-4o-mini"
        )
        self._api_key = os.getenv("KERROS_OMNIROUTE_API_KEY", "")
        self._client = OpenAICompatClient(
            base_url=self._base_url,
            model=self._model,
            api_key=self._api_key,
            provider_name="omniroute",
        )

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[list[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        if not self._enabled:
            raise RuntimeError("omniroute adapter is disabled")
        return self._client.complete(
            prompt,
            system=system,
            history=history,
            max_tokens=max_tokens,
            **kwargs,
        )

    def status(self) -> dict[str, Any]:
        if not self._enabled:
            return {
                "provider": "omniroute",
                "enabled": False,
                "base_url": self._base_url,
                "model": self._model,
                "available": False,
                "last_error": "",
            }
        status = self._client.status()
        status["enabled"] = self._enabled
        return status

    def available(self) -> bool:
        return self._enabled and self._client.available()
