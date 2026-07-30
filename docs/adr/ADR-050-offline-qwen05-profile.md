# ADR-050: Offline Qwen 0.5B Profile (Phase A)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Operators want a well-structured **offline AI Assistant** baseline:

Qwen2.5-0.5B-Instruct → GGUF Q4_K_M → llama.cpp → ChatML

KerrOS already had a Termux `ModelLoader`/`Generator` path and
Ollama/vLLM LLMPorts, but they were not unified under one offline
profile or composite provider.

## Decision

1. Add **`config/profiles/offline_qwen05.yaml`** as the Phase A profile
2. Add **`adapters/llm/llama_cpp_adapter.py`** (LLMPort) wrapping ChatML
   subprocess generation and optional `LLAMA_CPP_SERVER_ENDPOINT` HTTP
3. Add **`adapters/llm/offline_profile.py`** loader
4. Put **`llama_cpp` first** in the local-first composite chain when
   `KERROS_OFFLINE_PROFILE`, `KERROS_LLM_PROVIDER=llama_cpp`, or
   `KERROS_LOCAL_LLM=1`
5. Add **`scripts/download_qwen05_gguf.sh`** for the 0.5B Q4_K_M weight
6. Probe via `probe_llama_cpp` + HealthMonitor

Out of scope (later phases): Unsloth LoRA export, nomic/FAISS RAG,
coding index, LiteLLM gateway compose, reranker.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Keep only Termux `LLMEngine` path | Not behind LLMPort / `/llm` |
| Default to Ollama for offline | Extra daemon; user chose llama.cpp |
| Bundle GGUF in git | Size / license |

## Consequences

**Positive:** One profile + one provider for offline chat without cloud.

**Negative:** Operator must supply llama.cpp binary + download GGUF.

## Revisit when

Phase B (embeddings/vector), Phase C (coding index), Phase D (Unsloth
export), or Phase E (LiteLLM + llama.cpp server compose).
