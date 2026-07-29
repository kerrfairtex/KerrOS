# ADR-001: AI Provider Strategy — Groq as Primary

**Status:** Accepted  

**Date:** 2026-07-20  
**Accepted:** 2026-07-29

## Context
KerrOS runs cloud AI calls through `core/multi_api.py`'s multi-API fallback chain, developed under real constraints: mobile-only hardware (Termux, ~3.7GB RAM), zero/near-zero budget, and iterative sessions where fast turnaround matters more than raw throughput. The provider chosen as primary needed to be free with no card required, fast enough not to stall an interactive coding loop, and easy to integrate (OpenAI-compatible request/response shape keeps `multi_api.py` simple).

## Decision
Groq is primary in the fallback chain for interactive/chat paths. Current free-tier terms (verified July 2026): no credit card required, full access to hosted models, rate-limited at the organization level (roughly 30 requests/minute and 1,000–14,400 requests/day depending on model), with inference speed of 300–1,000+ tokens/sec on Groq's LPU hardware — typically 3–10x faster than typical GPU-based inference. That latency advantage is the deciding factor for an interactive coding loop.

Code evidence (`core/multi_api.py`): chat routing starts with Groq; coding/research/teaching/reasoning chains also fall back to Groq after task-specific providers. Local/self-hosted adapters (Ollama, vLLM, LiteLLM, OmniRoute) sit behind `LLMPort` / `CompositeLLMAdapter` and can be preferred via `KERROS_LLM_PROVIDER` or `KERROS_LOCAL_LLM` without changing this ADR's cloud-primary default.

## Alternatives considered
- **Google Gemini** — more generous free-tier volume and large context windows, but higher per-request latency than Groq's LPU. Strong first fallback, not primary.
- **OpenRouter** — aggregates many providers behind one API; adds a routing hop and an extra uptime dependency.
- **Cerebras** — also fast-inference-focused; narrower free developer access than Groq at time of review.
- **Together AI / Fireworks AI** — good open-weight pools; not differentiated enough to justify primary position.
- **DeepSeek / Mistral** — competitive model quality; more limited free API access than Groq or Gemini.

## Consequences
Groq's per-minute caps are tight enough that bursty or parallel multi-agent calls can hit 429s — that is exactly what the fallback chain and `CompositeLLMAdapter` exist to absorb. Standardizing on an OpenAI-compatible request shape as primary shaped `LLMPort` and the OpenAI-compat local adapters (KOS-005 / Phase 3).

## Revisit when
- Groq's free-tier terms change materially (stricter limits, credit card requirement added)
- Rate limits are observed blocking real usage, not just theoretically tight
- Self-hosted models via vLLM/Ollama become the default path for most sessions (`KERROS_LOCAL_LLM=1` / GPU funded)
