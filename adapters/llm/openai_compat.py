"""
adapters/llm/openai_compat.py
==============================
Shared OpenAI-compatible HTTP client for local LLM backends.

Ollama, vLLM, LM Studio, and llama.cpp server all expose /v1/chat/completions.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

import requests


def _build_messages(
    prompt: str,
    system: Optional[str],
    history: Optional[List[dict]],
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})
    return messages


class OpenAICompatClient:
    """Minimal OpenAI chat-completions client."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 120.0,
        provider_name: str = "openai_compat",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.provider_name = provider_name
        self.last_error = ""

    def available(self) -> bool:
        try:
            url = f"{self.base_url}/models"
            headers = self._headers()
            r = requests.get(url, headers=headers, timeout=5)
            return r.status_code < 500
        except Exception:
            return False

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        model = kwargs.get("model", self.model)
        messages = _build_messages(prompt, system, history)
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if "temperature" in kwargs:
            body["temperature"] = kwargs["temperature"]

        headers = self._headers()
        try:
            r = requests.post(url, headers=headers, json=body, timeout=self.timeout)
            data = r.json()
            if r.status_code >= 400:
                self.last_error = str(data)
                raise RuntimeError(f"{self.provider_name} HTTP {r.status_code}: {data}")
            content = data["choices"][0]["message"]["content"]
            self.last_error = ""
            return content
        except Exception as exc:
            self.last_error = str(exc)
            raise

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "base_url": self.base_url,
            "model": self.model,
            "available": self.available(),
            "last_error": self.last_error,
        }


def endpoint_from_env(env_var: str, default: str) -> str:
    return os.getenv(env_var, default).rstrip("/")
