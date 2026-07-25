"""
adapters/llm/composite_adapter.py
===================================
Composite LLMPort — local-first with cloud fallback.

Phase 3: Ollama and vLLM sit behind the existing LLMPort without kernel changes.
Provider selection via kwargs provider_hint or KERROS_LLM_PROVIDER env.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional


_LOCAL_PROVIDERS = ("ollama", "vllm", "local")


class CompositeLLMAdapter:
    """Routes completions to local or cloud adapters."""

    def __init__(self) -> None:
        self._cloud = None
        self._ollama = None
        self._vllm = None
        self._last_api: str | None = None
        self._default_provider = os.getenv("KERROS_LLM_PROVIDER", "cloud").lower()
        self._local_first = os.getenv("KERROS_LOCAL_LLM", "").lower() in (
            "1",
            "true",
            "yes",
        )

    def _get_cloud(self):
        if self._cloud is None:
            from adapters.llm.multi_api_adapter import MultiAPIAdapter
            self._cloud = MultiAPIAdapter()
        return self._cloud

    def _get_ollama(self):
        if self._ollama is None:
            from adapters.llm.ollama_adapter import OllamaAdapter
            self._ollama = OllamaAdapter()
        return self._ollama

    def _get_vllm(self):
        if self._vllm is None:
            from adapters.llm.vllm_adapter import VLLMAdapter
            self._vllm = VLLMAdapter()
        return self._vllm

    @property
    def engine(self):
        """Expose cloud engine for legacy callers (adaptive_engine)."""
        return getattr(self._get_cloud(), "engine", None)

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        provider = (kwargs.get("provider_hint") or self._default_provider).lower()
        chain = self._build_chain(provider)

        errors: list[str] = []
        for name, adapter in chain:
            try:
                if name in _LOCAL_PROVIDERS and not adapter.status().get("available"):
                    continue
                result = adapter.complete(
                    prompt,
                    system=system,
                    history=history,
                    max_tokens=max_tokens,
                    **{k: v for k, v in kwargs.items() if k != "provider_hint"},
                )
                self._last_api = name
                return result
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        if errors:
            raise RuntimeError("all LLM providers failed: " + "; ".join(errors))
        raise RuntimeError("no LLM providers configured")

    def _build_chain(self, provider: str) -> list[tuple[str, Any]]:
        if provider == "ollama":
            return [("ollama", self._get_ollama()), ("cloud", self._get_cloud())]
        if provider == "vllm":
            return [("vllm", self._get_vllm()), ("cloud", self._get_cloud())]
        if provider in _LOCAL_PROVIDERS or self._local_first:
            return [
                ("ollama", self._get_ollama()),
                ("vllm", self._get_vllm()),
                ("cloud", self._get_cloud()),
            ]
        return [("cloud", self._get_cloud())]

    def status(self) -> dict[str, Any]:
        cloud_status: dict[str, Any] = {}
        try:
            cloud_status = self._get_cloud().status()
        except Exception as exc:
            cloud_status = {"error": str(exc)}
        return {
            "default_provider": self._default_provider,
            "local_first": self._local_first,
            "last_api": self._last_api,
            "ollama": self._get_ollama().status(),
            "vllm": self._get_vllm().status(),
            "cloud": cloud_status,
        }

    def last_api_used(self) -> Optional[str]:
        return self._last_api
