"""
adapters/tts/chatterbox_adapter.py
====================================
TTS adapter for Resemble AI's Chatterbox (open-source TTS).

Chatterbox (https://github.com/resemble-ai/chatterbox) is an open-source,
locally-hostable text-to-speech model.  When served, it exposes a simple
REST endpoint for synthesis.

Self-hosting::

    # Install and run the Chatterbox inference server
    pip install chatterbox-tts
    python -m chatterbox.server --port 8055

Environment variables:
  CHATTERBOX_ENDPOINT   Local server URL (default: http://localhost:8055)
  CHATTERBOX_API_KEY    Optional API key if your deployment requires auth

Usage::

    from adapters.tts.chatterbox_adapter import ChatterboxAdapter
    tts = ChatterboxAdapter()
    audio_bytes = tts.synthesize("Hello from KerrOS!")
    with open("output.wav", "wb") as f:
        f.write(audio_bytes)
"""

from __future__ import annotations

import os
from typing import Any

import requests


class ChatterboxAdapter:
    """TTS adapter for a local Chatterbox inference server."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._base_url = (
            endpoint
            or os.getenv("CHATTERBOX_ENDPOINT", "http://localhost:8055")
        ).rstrip("/")
        self._api_key = api_key or os.getenv("CHATTERBOX_API_KEY", "")
        self.last_error = ""

    # ── Public API ────────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        *,
        voice: str = "default",
        speed: float = 1.0,
        **kwargs: Any,
    ) -> bytes:
        """Synthesize speech from text and return raw audio bytes (WAV).

        Args:
            text:   Input text to speak.
            voice:  Speaker/voice ID (model-dependent).
            speed:  Playback speed multiplier (1.0 = normal).
            **kwargs: Forwarded verbatim to the server request body.

        Returns:
            WAV audio bytes.
        """
        url = f"{self._base_url}/synthesize"
        body: dict[str, Any] = {
            "text": text,
            "voice": voice,
            "speed": speed,
            **kwargs,
        }
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"******"
        try:
            r = requests.post(url, json=body, headers=headers, timeout=60)
            if r.status_code >= 400:
                self.last_error = r.text
                raise RuntimeError(f"Chatterbox HTTP {r.status_code}: {r.text}")
            self.last_error = ""
            return r.content
        except Exception as exc:
            self.last_error = str(exc)
            raise

    def available(self) -> bool:
        """Return True if the Chatterbox server is reachable."""
        try:
            r = requests.get(f"{self._base_url}/health", timeout=5)
            return r.status_code < 500
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {
            "provider": "chatterbox",
            "base_url": self._base_url,
            "available": self.available(),
            "last_error": self.last_error,
        }
