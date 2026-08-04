"""
adapters/llm/openrouter_adapter.py
===================================
Zero-cost-first OpenRouter adapter for KerrOS.

Design goals (per /goal APPLY TO MY PROJECT):
  1. Free-tier by default. A paid model is only ever called if the caller
     passes allow_paid=True explicitly — no silent spend.
  2. Respects OpenRouter's real limits so you get a clean local backoff
     instead of a wasted 429: 20 req/min hard cap (all :free ids), 50/day
     unfunded or 1000/day once $10+ credits have ever been purchased.
  3. Free models on OpenRouter rotate out without notice. This adapter
     tracks dead models per-session (same pattern as your MultiAPIEngine
     .dead_apis) and skips them for the rest of the run instead of
     re-trying a slug that's already 404ing.
  4. Task -> tier routing reuses the same task buckets your multi_api.py
     already detects (coding/math, research, reasoning, teaching, chat),
     so this adapter is a drop-in *provider* inside that existing routing
     logic, not a competing router.

Wire-up (see README in this patch for the full diff):
    from adapters.llm.openrouter_adapter import OpenRouterAdapter
    adapter = OpenRouterAdapter()
    reply = adapter.complete("explain this stack trace", tier="coding")
"""

from __future__ import annotations

import os
import time
import threading
from pathlib import Path
from typing import Any, Optional

import requests

try:
    import yaml
except ImportError as e:  # pragma: no cover
    raise ImportError("pyyaml required: pip install pyyaml") from e

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_a, **_k):
        return False

_BASE = Path(os.path.expanduser("~/offline_ai"))
load_dotenv(_BASE / ".env")
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

DEFAULT_CONFIG_PATH = Path(
    os.getenv("KERROS_OPENROUTER_CONFIG", "")
    or (Path(__file__).resolve().parent.parent.parent / "config" / "openrouter_tiers.yaml")
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# OpenRouter's documented free-tier limits (mid-2026). If OpenRouter changes
# these, update here — the adapter has no way to discover them at runtime.
FREE_RPM = 20
FREE_RPD_UNFUNDED = 50
FREE_RPD_FUNDED = 1000


class _RateLimiter:
    """Local sliding-window limiter so we back off before OpenRouter does."""

    def __init__(self, rpm: int, rpd: int):
        self.rpm = rpm
        self.rpd = rpd
        self._minute_hits: list[float] = []
        self._day_hits: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> tuple[bool, str]:
        now = time.time()
        with self._lock:
            self._minute_hits = [t for t in self._minute_hits if now - t < 60]
            self._day_hits = [t for t in self._day_hits if now - t < 86400]
            if len(self._minute_hits) >= self.rpm:
                return False, f"local rpm cap ({self.rpm}/min) reached — wait a few seconds"
            if len(self._day_hits) >= self.rpd:
                return False, f"local rpd cap ({self.rpd}/day) reached — resets in <24h or buy $10 credits for {FREE_RPD_FUNDED}/day"
            return True, ""

    def record(self) -> None:
        now = time.time()
        with self._lock:
            self._minute_hits.append(now)
            self._day_hits.append(now)


class OpenRouterAdapter:
    """LLMPort-style adapter: available(), complete(), status(), last_api_used()."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        config_path: Path | None = None,
        daily_cap: int = FREE_RPD_UNFUNDED,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self._cfg = self._load_config(config_path or DEFAULT_CONFIG_PATH)
        self._limiter = _RateLimiter(rpm=FREE_RPM, rpd=daily_cap)
        self.dead_models: set[str] = set()
        self.health: dict[str, str] = {}
        self.last_api: str | None = None

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {"tiers": {}}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"tiers": {}}

    def available(self) -> bool:
        return bool(self.api_key)

    def _candidates(self, tier: str, allow_paid: bool) -> list[dict[str, Any]]:
        entries = list(self._cfg.get("tiers", {}).get(tier, []))
        if not allow_paid:
            entries = [e for e in entries if e.get("free", True)]
        # skip anything already marked dead this session
        return [e for e in entries if e.get("id") not in self.dead_models]

    def _post(self, model_id: str, messages: list[dict], max_tokens: int) -> tuple[Optional[str], Optional[str]]:
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://kerros.local",
                    "X-Title": "KerrOS",
                },
                json={"model": model_id, "messages": messages, "max_tokens": max_tokens},
                timeout=30,
            )
            data = resp.json()
            if resp.status_code >= 400 or "choices" not in data:
                err = data.get("error", {}).get("message", str(data))
                return None, f"{resp.status_code}: {err}"

            choice = data["choices"][0]
            content = choice.get("message", {}).get("content")
            if not content:
                # 200 OK but nothing usable came back — surface *why*
                # instead of collapsing to an opaque "unknown". Common
                # causes: upstream provider overloaded, moderation
                # refusal (check "refusal" field), or the model put
                # everything into "reasoning" and left content empty.
                refusal = choice.get("message", {}).get("refusal")
                finish = choice.get("finish_reason")
                return None, f"empty content (finish_reason={finish}, refusal={refusal})"
            return content, None
        except Exception as e:  # network / timeout / malformed JSON
            return None, f"{type(e).__name__}: {e}"

    def _is_dead_error(self, err: str) -> bool:
        e = err.lower()
        return any(s in e for s in (
            "400", "404", "410", "model_not_found", "not a valid model",
            "no longer available", "has been deprecated",
        ))

    def complete(
        self,
        prompt: str,
        *,
        tier: str = "chat",
        system: Optional[str] = None,
        history: Optional[list[dict]] = None,
        max_tokens: int = 1024,
        allow_paid: bool = False,
        **_: Any,
    ) -> str:
        if not self.available():
            return "[openrouter] OPENROUTER_API_KEY not set"

        candidates = self._candidates(tier, allow_paid)
        if not candidates:
            return f"[openrouter] no live candidates left in tier '{tier}' (allow_paid={allow_paid})"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        for m in history or []:
            if m.get("role") in ("user", "assistant"):
                messages.append(m)
        messages.append({"role": "user", "content": prompt})

        for entry in candidates:
            model_id = entry["id"]
            ok, reason = self._limiter.allow()
            if not ok:
                self.health[model_id] = f"rate-limited: {reason}"
                continue

            result, err = self._post(model_id, messages, max_tokens)
            self._limiter.record()

            if result:
                self.last_api = model_id
                self.health[model_id] = "ok"
                return result

            if err and self._is_dead_error(err):
                self.dead_models.add(model_id)
                self.health[model_id] = f"dead: {err[:80]}"
            else:
                self.health[model_id] = f"failed: {(err or 'unknown')[:80]}"

        return f"[openrouter] all candidates in tier '{tier}' failed — see .health for detail"

    def status(self) -> dict[str, Any]:
        tiers = self._cfg.get("tiers") or {}
        return {
            "provider": "openrouter",
            "available": self.available(),
            "key_set": bool(self.api_key),
            "config": str(DEFAULT_CONFIG_PATH),
            "tiers": sorted(tiers.keys()) if isinstance(tiers, dict) else [],
            "dead_models": sorted(self.dead_models),
            "health": dict(self.health),
            "rate_limit": {"rpm": FREE_RPM, "rpd": self._limiter.rpd},
            "setup_hint": (
                None
                if self.api_key
                else "Set OPENROUTER_API_KEY in ~/offline_ai/.env (see .env.example)"
            ),
        }

    def last_api_used(self) -> str | None:
        return self.last_api
