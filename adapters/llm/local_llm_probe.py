"""
adapters/llm/local_llm_probe.py
================================
Health probes for self-hosted OpenAI-compatible LLMs (C-19 / ADR-016).

Ollama and vLLM adapters already implement LLMPort; this module reports
component health for HealthMonitor without requiring a completion call.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

from adapters.llm.openai_compat import endpoint_from_env


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def is_ollama_enabled(cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or {}
    if _truthy(os.getenv("KERROS_OLLAMA_ENABLED", data.get("ollama_enabled", False))):
        return True
    provider = (
        os.getenv("KERROS_LLM_PROVIDER")
        or str(data.get("llm_provider_default") or "")
    ).lower()
    if provider == "ollama":
        return True
    if _truthy(os.getenv("KERROS_LOCAL_LLM", data.get("local_llm", False))):
        return True
    return False


def is_vllm_enabled(cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or {}
    if _truthy(os.getenv("KERROS_VLLM_ENABLED", data.get("vllm_enabled", False))):
        return True
    provider = (
        os.getenv("KERROS_LLM_PROVIDER")
        or str(data.get("llm_provider_default") or "")
    ).lower()
    if provider == "vllm":
        return True
    # Local-first tries ollama then vllm — treat both as opted-in for health.
    if _truthy(os.getenv("KERROS_LOCAL_LLM", data.get("local_llm", False))):
        return True
    return False


def resolve_ollama_url(cfg: dict[str, Any] | None = None) -> str:
    _ = cfg
    return endpoint_from_env("OLLAMA_ENDPOINT", "http://127.0.0.1:11434/v1").rstrip("/")


def resolve_vllm_url(cfg: dict[str, Any] | None = None) -> str:
    _ = cfg
    return endpoint_from_env("VLLM_ENDPOINT", "http://127.0.0.1:8000/v1").rstrip("/")


def _probe_models(
    *,
    provider: str,
    base_url: str,
    enabled: bool,
    api_key: str = "",
    timeout: float = 2.0,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "provider": provider,
        "enabled": enabled,
        "base_url": base_url,
        "available": False,
        "status": "disabled",
        "models": 0,
    }
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        r = requests.get(f"{base_url}/models", headers=headers, timeout=timeout)
        available = r.status_code < 500
        result["available"] = available
        result["http_status"] = r.status_code
        if available:
            try:
                data = r.json()
                models = data.get("data") if isinstance(data, dict) else None
                if isinstance(models, list):
                    result["models"] = len(models)
            except Exception:
                pass
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


def probe_ollama(
    base_url: Optional[str] = None,
    *,
    timeout: float = 2.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        from kernel.config import load_config

        cfg = dict(config or load_config().values)
    except Exception:
        cfg = dict(config or {})
    url = (base_url or resolve_ollama_url(cfg)).rstrip("/")
    return _probe_models(
        provider="ollama",
        base_url=url,
        enabled=is_ollama_enabled(cfg),
        timeout=timeout,
    )


def probe_vllm(
    base_url: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
    timeout: float = 2.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        from kernel.config import load_config

        cfg = dict(config or load_config().values)
    except Exception:
        cfg = dict(config or {})
    url = (base_url or resolve_vllm_url(cfg)).rstrip("/")
    key = (
        api_key
        if api_key is not None
        else (os.getenv("VLLM_API_KEY") or str(cfg.get("vllm_api_key") or ""))
    )
    return _probe_models(
        provider="vllm",
        base_url=url,
        enabled=is_vllm_enabled(cfg),
        api_key=str(key or "").strip(),
        timeout=timeout,
    )
