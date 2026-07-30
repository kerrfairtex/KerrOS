"""
adapters/llm/llama_cpp_adapter.py
=================================
LLMPort adapter for local llama.cpp (Phase A / ADR-050).

Two modes:
  1. **subprocess** — ChatML prompt via ``models.engine.generator`` + GGUF
  2. **http** — OpenAI-compat when ``LLAMA_CPP_SERVER_ENDPOINT`` is set

Default-off until binary+GGUF exist or HTTP endpoint is reachable.
Never hard-fails the process (unlike ``ModelLoader.validate()``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional

from adapters.llm.offline_profile import (
    is_offline_profile_active,
    load_offline_profile,
    profile_gguf_path,
    profile_prompt_format,
)
from adapters.llm.openai_compat import OpenAICompatClient
from models.engine.generator import Generator, build_chatml_prompt
from models.engine.loader import ModelLoader


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def is_llama_cpp_enabled(cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or {}
    if _truthy(os.getenv("KERROS_LLAMA_CPP_ENABLED", data.get("llama_cpp_enabled", False))):
        return True
    provider = (
        os.getenv("KERROS_LLM_PROVIDER")
        or str(data.get("llm_provider_default") or "")
    ).lower()
    if provider in ("llama_cpp", "llamacpp", "offline"):
        return True
    if is_offline_profile_active(data):
        return True
    if _truthy(os.getenv("KERROS_LOCAL_LLM", data.get("local_llm", False))):
        return True
    return False


class LlamaCppAdapter:
    """LLMPort implementation for llama.cpp (subprocess or HTTP)."""

    def __init__(
        self,
        *,
        model_path: str | None = None,
        binary: str | None = None,
        server_endpoint: str | None = None,
        profile: dict[str, Any] | None = None,
        prefer_light: bool = True,
        generator: Generator | None = None,
    ) -> None:
        self._profile = profile if profile is not None else load_offline_profile()
        self.prompt_format = profile_prompt_format(self._profile)
        self.last_api = "llama_cpp"
        self._generator = generator

        if server_endpoint is not None:
            http = str(server_endpoint).strip()
        else:
            http = os.getenv("LLAMA_CPP_SERVER_ENDPOINT", "").strip()
        self._http_client: OpenAICompatClient | None = None
        if http:
            base = http if "://" in http else f"http://{http}"
            model_name = os.getenv("LLAMA_CPP_MODEL", "qwen0.5b-q4")
            self._http_client = OpenAICompatClient(
                base_url=base.rstrip("/"),
                model=model_name,
                provider_name="llama_cpp",
            )

        self._loader = ModelLoader(prefer_light=prefer_light)
        if binary:
            self._loader.binary = binary
        if model_path:
            self._loader.model = str(Path(model_path).expanduser())
        elif self._profile:
            gguf = profile_gguf_path(self._profile)
            # Prefer profile GGUF when present; else keep ModelLoader resolution.
            if gguf.exists() or not self._loader.model:
                self._loader.model = str(gguf)
            elif not Path(self._loader.model).exists():
                self._loader.model = str(gguf)

    def _get_generator(self) -> Generator:
        if self._generator is None:
            self._generator = Generator(self._loader)
        return self._generator

    def _subprocess_ready(self) -> bool:
        binary = Path(self._loader.binary).expanduser() if self._loader.binary else None
        model = Path(self._loader.model).expanduser() if self._loader.model else None
        return bool(binary and binary.is_file() and model and model.is_file())

    def _http_ready(self) -> bool:
        if self._http_client is None:
            return False
        return bool(self._http_client.available())

    def available(self) -> bool:
        return self._subprocess_ready() or self._http_ready()

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[List[dict]] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        # Prefer HTTP server when configured and reachable; else subprocess.
        if self._http_client is not None and self._http_ready():
            self.last_api = "llama_cpp"
            return self._http_client.complete(
                prompt,
                system=system,
                history=history,
                max_tokens=max_tokens,
                **kwargs,
            )

        if not self._subprocess_ready():
            return (
                "[llama_cpp] binary or GGUF missing — "
                "set LLAMA_BIN + MODEL_PATH or run ./scripts/download_qwen05_gguf.sh"
            )

        original_max = self._loader.max_tokens
        try:
            self._loader.max_tokens = int(kwargs.get("max_tokens", max_tokens) or max_tokens)
            if self.prompt_format == "chatml":
                chatml = build_chatml_prompt(
                    system=system or "You are a helpful assistant.",
                    history=history or [],
                    user_message=prompt,
                )
            else:
                chatml = prompt
            return self._get_generator().generate(chatml, stream=False)
        finally:
            self._loader.max_tokens = original_max
            self.last_api = "llama_cpp"

    def status(self) -> dict[str, Any]:
        enabled = is_llama_cpp_enabled()
        subprocess_ok = self._subprocess_ready()
        http_ok = self._http_ready()
        available = subprocess_ok or http_ok
        mode = "http" if http_ok else ("subprocess" if subprocess_ok else "none")
        return {
            "provider": "llama_cpp",
            "enabled": enabled,
            "available": available,
            "mode": mode,
            "prompt_format": self.prompt_format,
            "binary": self._loader.binary or "",
            "model": self._loader.model or "",
            "profile": (self._profile or {}).get("name") or "",
            "http": bool(self._http_client),
            "status": (
                "ok"
                if available
                else ("disabled" if not enabled else "unavailable")
            ),
        }

    def last_api_used(self) -> str | None:
        return self.last_api
