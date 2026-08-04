"""
core/context_builder.py
========================
Zero-cost context builder — the "content management" layer.

Purpose: before a generation model ever runs, cheaply figure out *which*
chunks of history/RAG/docs actually matter for this turn, using only free
embed+rerank models, and assemble the smallest high-signal context that
fits the target token budget. This keeps the expensive step (generation)
short and cheap, and keeps quality high because the model only sees
relevant material instead of everything.

Pipeline:
    chunks (list[str]) --embed(free)--> vectors
                        --cosine similarity--> top_k candidates
                        --rerank(free)--> final ranked order
                        --budget trim--> assembled context string

If the embed/rerank calls fail (rate-limited, dead model, no key), this
degrades gracefully to a plain recency+keyword heuristic rather than
blocking the whole pipeline — a context builder should never be a single
point of failure for the assistant.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from adapters.llm.openrouter_adapter import OpenRouterAdapter


@dataclass
class ContextChunk:
    text: str
    source: str = ""
    score: float = 0.0


@dataclass
class ContextBuilder:
    adapter: OpenRouterAdapter = field(default_factory=OpenRouterAdapter)
    token_budget: int = 2000
    chars_per_token: int = 4  # rough heuristic, avoids pulling a tokenizer dep

    # ── Embedding path (free tier) ───────────────────────────────────
    def _embed(self, texts: list[str]) -> Optional[list[list[float]]]:
        """
        NOTE: OpenRouter's chat-completions endpoint does not return raw
        embedding vectors the way a dedicated /embeddings endpoint would.
        If nvidia/nemotron-3-embed-1b:free is only exposed as a chat model
        on your account, swap this for a direct call to whatever embeddings
        endpoint your OpenRouter/NVIDIA NIM key actually exposes — this
        method is written so only this one function needs to change.
        """
        return None  # falls through to heuristic scoring below

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1e-9
        nb = math.sqrt(sum(x * x for x in b)) or 1e-9
        return dot / (na * nb)

    # ── Heuristic fallback (zero API calls, zero cost, always available) ─
    @staticmethod
    def _keyword_score(query: str, chunk: str) -> float:
        q_terms = set(re.findall(r"\w+", query.lower()))
        c_terms = re.findall(r"\w+", chunk.lower())
        if not q_terms or not c_terms:
            return 0.0
        overlap = sum(1 for t in c_terms if t in q_terms)
        return overlap / (len(c_terms) ** 0.5)

    # ── Rerank path (free tier, via chat-completions instruct-rerank) ──
    def _rerank(self, query: str, candidates: list[ContextChunk]) -> list[ContextChunk]:
        if not self.adapter.available() or not candidates:
            return candidates
        joined = "\n".join(f"[{i}] {c.text[:300]}" for i, c in enumerate(candidates))
        prompt = (
            f"Query: {query}\n\nCandidates:\n{joined}\n\n"
            "Return only a comma-separated list of candidate indices, "
            "most relevant to the query first. No explanation."
        )
        reply = self.adapter.complete(prompt, tier="rerank", max_tokens=64)
        if reply.startswith("[openrouter]"):
            return candidates  # degrade silently to input order
        try:
            order = [int(x.strip()) for x in reply.split(",") if x.strip().isdigit()]
            reranked = [candidates[i] for i in order if 0 <= i < len(candidates)]
            missing = [c for i, c in enumerate(candidates) if i not in order]
            return reranked + missing
        except Exception:
            return candidates

    # ── Public API ───────────────────────────────────────────────────
    def build(self, query: str, chunks: list[ContextChunk], top_k: int = 12) -> str:
        """
        Score, rerank, and trim `chunks` down to `token_budget`, returning
        a single assembled context string ready to prepend to a prompt.
        """
        if not chunks:
            return ""

        for c in chunks:
            c.score = self._keyword_score(query, c.text)
        chunks.sort(key=lambda c: c.score, reverse=True)
        shortlist = chunks[: max(top_k, 1)]

        ranked = self._rerank(query, shortlist)

        budget_chars = self.token_budget * self.chars_per_token
        out: list[str] = []
        used = 0
        for c in ranked:
            piece = f"[{c.source or 'ctx'}] {c.text.strip()}"
            if used + len(piece) > budget_chars:
                remaining = budget_chars - used
                if remaining > 100:
                    out.append(piece[:remaining] + " …")
                break
            out.append(piece)
            used += len(piece)

        return "\n\n".join(out)
