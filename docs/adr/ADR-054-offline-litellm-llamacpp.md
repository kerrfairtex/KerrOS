# ADR-054: Offline LiteLLM + llama.cpp Server Compose (Phase E)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

[ADR-050](ADR-050-offline-qwen05-profile.md) through
[ADR-053](ADR-053-unsloth-lora-gguf-export.md) shipped the offline combo
through Unsloth→GGUF. Phase E adds the **OpenAI-compatible gateway**:
llama.cpp server + optional LiteLLM sidecar on loopback, so KerrOS can
use `LITELLM_ENDPOINT` / `LLAMA_CPP_SERVER_ENDPOINT` without cloud.

## Decision

1. Add **`deploy/llama_cpp/`** compose with profiles `llama_cpp`,
   `litellm`, `proxy` (bare `up` is a no-op; loopback-only ports)
2. Mount host `models/*.gguf` read-only (operator-owned weights)
3. LiteLLM config routes `qwen0.5b-q4` → `http://llama-cpp:8080/v1`
4. Add **`scripts/llama_cpp_docker.sh`** with loopback guard +
   `plan` / `up` / `probe`
5. Add **`adapters/llm/offline_gateway.py`** Fake planner;
   `production_gateway` stays False
6. Probe LiteLLM via `probe_litellm`; wire HealthMonitor
7. Profile `litellm:` block (default-off) + runtime HTTP endpoint docs

Out of scope: public bind, production TLS seal, bundling GGUF in the
image, requiring Docker in CI.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Default-start without profiles | Accidental image pull on cloud VMs |
| Bundle GGUF in image | Size / license |
| Require live containers in CI | Soft Fake plan + YAML guards only |

## Consequences

**Positive:** Offline Combo has a documented OpenAI `/v1` gateway.

**Negative:** Operator must supply GGUF + Docker; image tags may drift.

## Revisit when

A funded deploy needs public LiteLLM/TLS, multi-node llama.cpp, or
reranker wiring on the same gateway.
