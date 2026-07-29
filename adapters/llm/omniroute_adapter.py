"""
adapters/llm/omniroute_adapter.py
=================================
OmniRoute-compatible LLM adapter over a single OpenAI-compatible endpoint.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

from adapters.llm.openai_compat import OpenAICompatClient
from kernel.flags import is_true
from kernel.config import load_config

DEFAULT_OMNIROUTE_URL = "http://127.0.0.1:20128/v1"


def resolve_omniroute_url(cfg: Optional[dict[str, Any]] = None) -> str:
    """Resolve OmniRoute base URL.

    Priority: OMNIROUTE_ENDPOINT → KERROS_OMNIROUTE_URL → config omniroute_url → default.
    """
    if cfg is None:
        cfg = load_config().values
    return (
        (os.getenv("OMNIROUTE_ENDPOINT") or "").strip()
        or (os.getenv("KERROS_OMNIROUTE_URL") or "").strip()
        or str(cfg.get("omniroute_url") or "").strip()
        or DEFAULT_OMNIROUTE_URL
    )


def is_omniroute_enabled(cfg: Optional[dict[str, Any]] = None) -> bool:
    """Whether OmniRoute is selected as an active LLM path."""
    if cfg is None:
        cfg = load_config().values
    enabled_cfg = cfg.get("use_omniroute", False)
    return is_true(os.getenv("KERROS_USE_OMNIROUTE", enabled_cfg))


def resolve_omniroute_api_key() -> str:
    return (
        (os.getenv("OMNIROUTE_API_KEY") or "").strip()
        or (os.getenv("KERROS_OMNIROUTE_API_KEY") or "").strip()
    )


def probe_omniroute(
    base_url: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
    timeout: float = 2.0,
) -> dict[str, Any]:
    """Probe OmniRoute OpenAI-compatible /models endpoint.

    Returns a component-shaped dict suitable for HealthMonitor.
    """
    cfg = load_config().values
    enabled = is_omniroute_enabled(cfg)
    url = (base_url or resolve_omniroute_url(cfg)).rstrip("/")
    key = api_key if api_key is not None else resolve_omniroute_api_key()
    headers: dict[str, str] = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    result: dict[str, Any] = {
        "provider": "omniroute",
        "enabled": enabled,
        "base_url": url,
        "available": False,
        "status": "disabled",
    }

    try:
        r = requests.get(f"{url}/models", headers=headers, timeout=timeout)
        available = r.status_code < 500
        result["available"] = available
        result["http_status"] = r.status_code
        if not enabled:
            result["status"] = "disabled"
        elif available:
            result["status"] = "ok"
        else:
            result["status"] = "unavailable"
            result["error"] = f"HTTP {r.status_code}"
    except Exception as exc:
        result["available"] = False
        result["error"] = str(exc)
        result["status"] = "disabled" if not enabled else "unavailable"

    return result


class OmniRouteAdapter:
    """LLM adapter for a unified local OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        cfg = load_config().values
        self._enabled = is_omniroute_enabled(cfg)
        self._base_url = resolve_omniroute_url(cfg)
        self._model = (
            os.getenv("KERROS_OMNIROUTE_MODEL")
            or cfg.get("omniroute_model")
            or "gpt-4o-mini"
        )
        self._api_key = resolve_omniroute_api_key()
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
