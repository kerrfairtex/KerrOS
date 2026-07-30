# ADR-016: Self-Hosted Local LLM Ops (C-19)

**Status:** Accepted  
**Date:** 2026-07-29

## Context

Backlog **C-19** is “self-hosted models via vLLM/Ollama” behind `LLMPort`.
Phase 3 already shipped `OllamaAdapter` and `VLLMAdapter` in
`CompositeLLMAdapter` (`KERROS_LOCAL_LLM=1`). What was missing was an **ops
foundation**: loopback Docker for Ollama, health probes, and an explicit ADR
so C-19 is no longer “deferred” while adapters silently exist.

## Decision

1. Keep adapters as the LLMPort implementation (no kernel change)
2. Add `adapters/llm/local_llm_probe.py` — `probe_ollama` / `probe_vllm`
3. Wire both into `HealthMonitor` (fail overall only when enabled + down)
4. Ship `deploy/ollama/` + `scripts/local_llm_docker.sh` (loopback `11434`)
5. Document vLLM as **bring-your-own GPU endpoint** (probe/env only; no heavy
   GPU image in-repo by default)

Enabled when `KERROS_LOCAL_LLM=1`, `KERROS_LLM_PROVIDER=ollama|vllm`, or
`KERROS_OLLAMA_ENABLED` / `KERROS_VLLM_ENABLED`.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Bundle a vLLM GPU compose in-repo | Image/weight size; cloud VM often has no GPU |
| Replace cloud default with local | Breaks Termux / keyless CI |
| New kernel service for models | Violates narrow LLMPort boundary |

## Consequences

**Positive:** Operators can run Ollama beside KerrOS; `/health` and `/llm`
reflect local availability; backlog C-19 marked foundation.

**Negative:** Pulling models is still a manual `ollama pull`; vLLM deploy
remains operator-owned.

## Revisit when

A funded GPU host needs a first-class `deploy/vllm/` kit — add compose then,
still behind the same probes/adapters.
