"""
core/router.py
===============
Single entry point for generation, replacing the split between
core/engine.py (simple cloud-fallback-chain + local) and
core/multi_api.py (task-routed chain across configured key providers).

Both of those files stay as-is and are reused here rather than rewritten,
so nothing that already works breaks. This module just adds a cost-aware
layer on top and picks between them:

    Priority (zero-cost-first, matches your engine.py docstring intent
    of "ONLINE first, LOCAL llama.cpp last", now with a free/paid split
    inside "online"):

    1. OpenRouterAdapter, free tier only, task-routed via config/openrouter_tiers.yaml
    2. MultiAPIEngine (core/multi_api.py) — your existing keyed providers
       (Groq, DeepSeek, Kimi, NVIDIA, etc.) — whatever you already pay for
       or already have free keys for
    3. LLMEngine local llama.cpp (core/engine.py) — always available,
       zero API cost, slowest/lowest quality
    4. Paid OpenRouter tier — ONLY if allow_paid=True is passed explicitly

Nothing above step 4 ever spends money.
"""

from __future__ import annotations

import logging
from typing import Optional

from adapters.llm.openrouter_adapter import OpenRouterAdapter
from core.multi_api import MultiAPIEngine, detect_task
from core.engine import LLMEngine
from core.context_builder import ContextBuilder, ContextChunk

log = logging.getLogger("kerros.router")

# task bucket -> openrouter tier name (config/openrouter_tiers.yaml)
_TASK_TO_TIER = {
    "coding": "coding",
    "math": "coding",
    "research": "research",
    "teaching": "chat",
    "reasoning": "reasoning",
    "chat": "chat",
}

# After the task tier, try free catch-all before leaving OpenRouter.
_OPENROUTER_FALLBACK_TIERS = ("auto",)


class Router:
    def __init__(self, *, system: str | None = None):
        self.openrouter = OpenRouterAdapter()
        self.multi_api = MultiAPIEngine()
        self.local = LLMEngine(system=system) if system else LLMEngine()
        self.context_builder = ContextBuilder()
        self.last_provider: str | None = None

    def build_context(self, query: str, raw_chunks: list[str], sources: list[str] | None = None) -> str:
        """Zero-cost content-management pass — call before generate() when
        you have RAG hits / history / files to fold in."""
        sources = sources or [""] * len(raw_chunks)
        chunks = [ContextChunk(text=t, source=s) for t, s in zip(raw_chunks, sources)]
        return self.context_builder.build(query, chunks)

    def generate(
        self,
        user_message: str,
        *,
        system: Optional[str] = None,
        history: Optional[list[dict]] = None,
        max_tokens: int = 1024,
        allow_paid: bool = False,
    ) -> str:
        history = history or []
        task = detect_task(user_message)
        tier = _TASK_TO_TIER.get(task, "chat")

        # 1. Free OpenRouter tiers — task bucket, then free catch-all
        if self.openrouter.available():
            for try_tier in (tier, *_OPENROUTER_FALLBACK_TIERS):
                reply = self.openrouter.complete(
                    user_message,
                    tier=try_tier,
                    system=system,
                    history=history,
                    max_tokens=max_tokens,
                    allow_paid=False,
                )
                if not reply.startswith("[openrouter]"):
                    self.last_provider = f"openrouter:{self.openrouter.last_api_used()}"
                    return reply
                log.debug(
                    "openrouter tier=%s exhausted for task=%s: %s",
                    try_tier,
                    task,
                    reply,
                )

        # 2. Existing keyed providers (whatever you've already configured)
        reply = self.multi_api.generate(user_message, system=system, history=history, max_tokens=max_tokens)
        if reply and "[All APIs failed" not in reply:
            self.last_provider = f"multi_api:{self.multi_api.last_api}"
            return reply

        # 3. Local llama.cpp — always free, always available, last resort
        try:
            reply = self.local.chat(user_message, history=history, stream=False, system=system)
            self.last_provider = "local:llama.cpp"
            return reply
        except Exception as e:
            log.debug("local fallback failed: %s", e)

        # 4. Paid OpenRouter + panel routers — opt-in only
        if allow_paid and self.openrouter.available():
            for try_tier in ("paid", "routers"):
                reply = self.openrouter.complete(
                    user_message,
                    tier=try_tier,
                    system=system,
                    history=history,
                    max_tokens=max_tokens,
                    allow_paid=True,
                )
                if not reply.startswith("[openrouter]"):
                    self.last_provider = f"openrouter-paid:{self.openrouter.last_api_used()}"
                    return reply

        self.last_provider = None
        return "[router] all free tiers exhausted, local unavailable, allow_paid=False — nothing left to try"

    def status(self) -> dict:
        return {
            "last_provider": self.last_provider,
            "openrouter": self.openrouter.status(),
            "multi_api_health": dict(self.multi_api.health),
            "multi_api_dead": sorted(self.multi_api.dead_apis),

        }

