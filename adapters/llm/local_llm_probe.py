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


def is_llama_cpp_probe_enabled(cfg: dict[str, Any] | None = None) -> bool:
    from adapters.llm.llama_cpp_adapter import is_llama_cpp_enabled

    return is_llama_cpp_enabled(cfg)


def probe_llama_cpp(
    *,
    timeout: float = 2.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Status probe for llama.cpp subprocess/HTTP (ADR-050)."""
    _ = timeout
    try:
        from kernel.config import load_config

        cfg = dict(config or load_config().values)
    except Exception:
        cfg = dict(config or {})
    enabled = is_llama_cpp_probe_enabled(cfg)
    try:
        from adapters.llm.llama_cpp_adapter import LlamaCppAdapter

        st = LlamaCppAdapter().status()
        st["enabled"] = enabled
        if st.get("available"):
            st["status"] = "ok"
        else:
            st["status"] = "unavailable" if enabled else "disabled"
        return st
    except Exception as exc:
        return {
            "provider": "llama_cpp",
            "enabled": enabled,
            "available": False,
            "status": "unavailable" if enabled else "disabled",
            "error": str(exc),
        }


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


def is_litellm_enabled(cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or {}
    if _truthy(os.getenv("KERROS_LITELLM_ENABLED", data.get("litellm_enabled", False))):
        return True
    provider = (
        os.getenv("KERROS_LLM_PROVIDER")
        or str(data.get("llm_provider_default") or "")
    ).lower()
    if provider == "litellm":
        return True
    if os.getenv("LITELLM_ENDPOINT", "").strip():
        return True
    try:
        from adapters.llm.offline_profile import (
            is_offline_profile_active,
            load_offline_profile,
        )

        if is_offline_profile_active(data):
            profile = load_offline_profile(cfg=data)
            litellm = profile.get("litellm") if isinstance(profile, dict) else None
            if isinstance(litellm, dict) and _truthy(litellm.get("enabled", False)):
                return True
    except Exception:
        pass
    return False


def resolve_litellm_url(cfg: dict[str, Any] | None = None) -> str:
    _ = cfg
    return endpoint_from_env("LITELLM_ENDPOINT", "http://127.0.0.1:4000/v1").rstrip("/")


def probe_litellm(
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
    url = (base_url or resolve_litellm_url(cfg)).rstrip("/")
    key = (
        api_key
        if api_key is not None
        else (os.getenv("LITELLM_API_KEY") or str(cfg.get("litellm_api_key") or ""))
    )
    return _probe_models(
        provider="litellm",
        base_url=url,
        enabled=is_litellm_enabled(cfg),
        api_key=str(key or "").strip(),
        timeout=timeout,
    )
