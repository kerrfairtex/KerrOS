# ADR-001: AI Provider Strategy — Groq as Primary

**Status:** DRAFT — reasoning below is reconstructed from stated priorities and current provider data, not yet confirmed as the actual historical reason. Edit the Context/Decision sections before treating this as final.

**Date:** 2026-07-20

## Context
KerrOS runs cloud AI calls through `core/multi_api.py`'s 8-API fallback chain, developed under real constraints: mobile-only hardware (Termux, ~3.7GB RAM), zero/near-zero budget, and iterative "vibe-coding" sessions where fast turnaround matters more than raw throughput. The provider chosen as primary needed to be free with no card required, fast enough not to stall an interactive coding loop, and easy to integrate (OpenAI-compatible request/response shape keeps `multi_api.py` simple).

## Decision
Groq is primary in the fallback chain. Confirmed current free-tier terms (verified July 2026): no credit card required, full access to all hosted models, rate-limited at the organization level to roughly 30 requests/minute and 1,000–14,400 requests/day depending on model, with inference speed of 300–1,000+ tokens/sec on Groq's LPU hardware — 3–10x faster than typical GPU-based inference. This speed advantage is likely the deciding factor for an interactive dev loop, though this should be confirmed, not assumed.

## Alternatives considered
- **Google Gemini** — more generous free-tier volume (reported ~1,500 requests/day, much higher tokens/minute than Groq's ~6–12K TPM cap) and large context windows, but noticeably slower per-request latency than Groq's LPU hardware. Strong candidate as first fallback rather than primary.
- **OpenRouter** — aggregates many providers behind one API, useful for reducing integration surface, but adds a routing hop and a dependency on OpenRouter's own uptime rather than the underlying model providers directly.
- **Cerebras** — also fast-inference-focused, narrower free developer access than Groq at time of review.
- **Together AI / Fireworks AI** — good for running many open-weight models through one API, not differentiated enough from Groq to justify primary position; reasonable pool for later fallback tiers.
- **DeepSeek / Mistral** — competitive model quality, but more limited free API access than Groq or Gemini.

## Consequences
Groq's per-minute caps (30 RPM, single-digit-thousands TPM depending on model) are tight enough that bursty or parallel multi-agent calls can hit 429s during heavy sessions — this is exactly what the fallback chain exists to absorb, not something Groq alone needs to solve. Standardizing on an OpenAI-compatible request shape as primary also shapes what `multi_api.py` and the future `LLMPort` adapter (KOS-005) assume as the common interface — swapping to a provider with a meaningfully different API shape would touch that adapter, not just a config value.

## Revisit when
- Groq's free-tier terms change materially (stricter limits, credit card requirement added)
- Rate limits are actually observed blocking real usage, not just theoretically tight
- Phase 3 triggers (JOTHAM revenue funds a GPU) — self-hosted models via vLLM/Ollama may reduce reliance on any cloud primary
