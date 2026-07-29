"""
adapters/llm/composite_adapter.py
===================================
Composite LLMPort — local-first with cloud fallback.

Phase 3: Ollama and vLLM sit behind the existing LLMPort without kernel changes.
Provider selection via kwargs provider_hint or KERROS_LLM_PROVIDER env.
P6: per-provider circuit breaker / cooldown / lockout via resilience registry.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from kernel.config import load_config
from adapters.llm.resilience import (
    ProviderCircuitRegistry,
    load_resilience_config,
    looks_like_provider_failure,
)


_LOCAL_PROVIDERS = ("ollama", "vllm", "local", "litellm")
_UNIFIED_PROVIDERS = ("omniroute", "gateway", "unified")


class CompositeLLMAdapter:
    """Routes completions to local or cloud adapters."""

    def __init__(self, resilience: ProviderCircuitRegistry | None = None) -> None:
        cfg = load_config().values
        self._cloud = None
        self._omniroute = None
        self._ollama = None
        self._vllm = None
        self._litellm = None
        self._last_api: str | None = None
        self._default_provider = os.getenv(
            "KERROS_LLM_PROVIDER",
            str(cfg.get("llm_provider_default", "cloud")),
        ).lower()
        self._local_first = os.getenv("KERROS_LOCAL_LLM", "").lower() in (
            "1",
            "true",
            "yes",
        )
        route_policy = str(cfg.get("llm_route_policy", "legacy_fallback")).strip().lower()
        self._unified_first = (
            os.getenv("KERROS_UNIFIED_FIRST", "").lower() in ("1", "true", "yes")
            or route_policy == "unified_first"
        )
        self._resilience = resilience or ProviderCircuitRegistry(
            config=load_resilience_config()
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

    def _get_omniroute(self):
        if self._omniroute is None:
            from adapters.llm.omniroute_adapter import OmniRouteAdapter
            self._omniroute = OmniRouteAdapter()
        return self._omniroute

    def _get_vllm(self):
        if self._vllm is None:
            from adapters.llm.vllm_adapter import VLLMAdapter
            self._vllm = VLLMAdapter()
        return self._vllm

    def _get_litellm(self):
        if self._litellm is None:
            from adapters.llm.litellm_adapter import LiteLLMAdapter
            self._litellm = LiteLLMAdapter()
        return self._litellm

    @property
    def engine(self):
        """Expose cloud engine for legacy callers (adaptive_engine)."""
        return getattr(self._get_cloud(), "engine", None)

    @property
    def resilience(self) -> ProviderCircuitRegistry:
        return self._resilience

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        provider = (kwargs.get("provider_hint") or self._default_provider).lower()
        chain = self._build_chain(provider)

        errors: list[str] = []
        for name, adapter in chain:
            if not self._resilience.allow(name):
                snap = self._resilience.snapshot()["providers"].get(name, {})
                errors.append(
                    f"{name}: circuit {snap.get('state', 'open')} "
                    f"(skip; cooldown={snap.get('cooldown_remaining_s', 0)}s "
                    f"lockout={snap.get('lockout_remaining_s', 0)}s)"
                )
                continue
            try:
                if name in _LOCAL_PROVIDERS and not adapter.status().get("available"):
                    self._resilience.record_failure(
                        name, error="provider unavailable", permanent=False
                    )
                    continue
                result = adapter.complete(
                    prompt,
                    system=system,
                    history=history,
                    max_tokens=max_tokens,
                    **{k: v for k, v in kwargs.items() if k != "provider_hint"},
                )
                if looks_like_provider_failure(result):
                    self._resilience.record_failure(
                        name, error=str(result)[:200], permanent=False
                    )
                    errors.append(f"{name}: {result}")
                    continue
                self._resilience.record_success(name)
                self._last_api = name
                return result
            except Exception as exc:
                permanent = _is_permanent(str(exc))
                self._resilience.record_failure(
                    name, error=str(exc), permanent=permanent
                )
                errors.append(f"{name}: {exc}")

        if errors:
            raise RuntimeError("all LLM providers failed: " + "; ".join(errors))
        raise RuntimeError("no LLM providers configured")

    def _build_chain(self, provider: str) -> list[tuple[str, Any]]:
        def _unified_chain() -> list[tuple[str, Any]]:
            return [("omniroute", self._get_omniroute()), ("cloud", self._get_cloud())]

        if provider in _UNIFIED_PROVIDERS:
            return _unified_chain()
        if provider == "ollama":
            return [("ollama", self._get_ollama()), ("cloud", self._get_cloud())]
        if provider == "vllm":
            return [("vllm", self._get_vllm()), ("cloud", self._get_cloud())]
        if provider == "litellm":
            return [("litellm", self._get_litellm()), ("cloud", self._get_cloud())]
        if self._unified_first:
            return _unified_chain()
        if provider in _LOCAL_PROVIDERS or self._local_first:
            return [
                ("ollama", self._get_ollama()),
                ("litellm", self._get_litellm()),
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
            "unified_first": self._unified_first,
            "last_api": self._last_api,
            "omniroute": self._get_omniroute().status(),
            "ollama": self._get_ollama().status(),
            "vllm": self._get_vllm().status(),
            "litellm": self._get_litellm().status(),
            "cloud": cloud_status,
            "resilience": self._resilience.snapshot(),
        }

    def reset_resilience(self, provider: str | None = None) -> list[str]:
        return self._resilience.reset(provider)

    def last_api_used(self) -> Optional[str]:
        return self._last_api


def _is_permanent(message: str) -> bool:
    lowered = (message or "").lower()
    markers = (
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "invalid api key",
        "no api key",
        "authentication",
    )
    return any(m in lowered for m in markers)
