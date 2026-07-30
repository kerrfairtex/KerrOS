# ADR-048: Soft vLLM Ops Kit (C-19)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

[ADR-016](ADR-016-local-llm-ops.md) shipped Ollama loopback compose + shared
Ollama/vLLM probes, and left vLLM as bring-your-own GPU. Operators asked for
a first-class `deploy/vllm/` on-ramp without bundling model weights or
requiring a GPU in CI.

## Decision

1. Add **`deploy/vllm/`** compose with **loopback `127.0.0.1:8000`** and a
   pinned `vllm/vllm-openai` image
2. Use Compose **profiles** (`vllm` GPU, `cpu` experimental) so bare
   `docker compose up` is a no-op
3. Add **`scripts/vllm_docker.sh`** with the same loopback port guard as
   `local_llm_docker.sh`
4. Keep existing `VLLMAdapter` / `probe_vllm` / HealthMonitor wiring
5. Model download, HF tokens, NVIDIA toolkit, and production auth/proxy stay
   **operator-owned**

CI only asserts compose artifacts (no live inference).

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Default-start without profiles | Accidental GPU image pull on cloud VMs |
| Bundle model weights in-repo | Size / license |
| Require GPU in CI | Breaks default checkout |

## Consequences

**Positive:** Funded GPU hosts have a documented kit beside Ollama.

**Negative:** CPU profile is experimental; GPU hosts still need toolkit +
weights.

## Revisit when

A funded deploy needs auth proxy, multi-node vLLM, or automated model
provisioning — not more soft stubs by default.
