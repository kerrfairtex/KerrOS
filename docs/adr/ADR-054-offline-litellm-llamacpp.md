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

## Pending — until live containers

Phase E is **compose + Fake plan only** until an operator (or funded
host) actually runs the stack:

```bash
./scripts/llama_cpp_docker.sh up --litellm   # live llama.cpp + LiteLLM
./scripts/llama_cpp_docker.sh probe          # GET /v1/models must succeed
```

Until then:

| Claim | Status |
|-------|--------|
| Compose YAML / loopback guards / `plan` | True (CI-covered) |
| Live OpenAI `/v1` completions via LiteLLM | **Not true** — needs running containers + GGUF |
| `production_gateway` | Always False (even after soft `allow_live` probe) |

Do not treat the offline combo as “gateway verified” until probe
against live containers passes on a named host.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Default-start without profiles | Accidental image pull on cloud VMs |
| Bundle GGUF in image | Size / license |
| Require live containers in CI | Soft Fake plan + YAML guards only |

## Consequences

**Positive:** Offline Combo has a documented OpenAI `/v1` gateway.

**Negative:** Operator must supply GGUF + Docker; image tags may drift;
live gateway is unproven until containers are up.

## Revisit when

Live containers are brought up and `llama_cpp_docker.sh probe` passes
on a named host; or a funded deploy needs public LiteLLM/TLS,
multi-node llama.cpp, or reranker wiring on the same gateway.
