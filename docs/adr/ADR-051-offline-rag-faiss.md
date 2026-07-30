# ADR-051: Offline RAG Phase B (nomic-embed + FAISS / FTS)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

[ADR-050](ADR-050-offline-qwen05-profile.md) shipped the offline LLM
baseline (Qwen 0.5B + llama.cpp + ChatML). Phase B adds the RAG half of
the Offline Combo: nomic embeddings + optional FAISS while keeping
SQLite FTS as primary ([ADR-015](ADR-015-qdrant-optional-vector-store.md)).

## Decision

1. **`adapters/embeddings/resolve.py`** — resolve model/dim/prefixes from
   env → config → offline profile → defaults (offline →
   `nomic-ai/nomic-embed-text-v1.5` @ 768; else MiniLM @ 384)
2. Update **`SentenceTransformersAdapter`** for configurable dim,
   nomic `trust_remote_code`, and search_query/document prefixes;
   hash-mock embeddings when sentence-transformers is absent (CI)
3. Add **`adapters/memory/faiss_vector_store.py`** — default-off soft
   store; `faiss` when installed, numpy cosine Fake otherwise;
   persist under `data/faiss/kerros_memory.npz`
4. **`HybridMemoryAdapter`** merges FTS + FAISS + Qdrant hits; FTS
   remains required, vectors additive
5. Offline profile `vector.optional: faiss` + `enabled: true` opts FAISS
   in when `KERROS_OFFLINE_PROFILE` is set
6. **pgvector** stays operator-owned / not default offline

Out of scope: live HF download in CI, reranker, coding index, Unsloth
export, LiteLLM gateway.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Make FAISS primary | Breaks offline hosts without numpy/faiss; contradicts ADR-015 |
| Default everyone to nomic 768 | Invalids existing MiniLM/Qdrant collections |
| Require faiss-cpu in CI | Soft Fake numpy path required |

## Consequences

**Positive:** Offline Combo RAG works with FTS alone; FAISS adds semantic
recall when enabled.

**Negative:** Switching embed dims requires rebuild of FAISS/Qdrant
indexes.

## Revisit when

Phase C (coding index), optional bge-reranker, or funded pgvector.
