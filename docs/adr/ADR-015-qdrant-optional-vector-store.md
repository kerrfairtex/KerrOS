# ADR-015: Optional Qdrant Vector Store (C-18)

**Status:** Accepted  
**Date:** 2026-07-29

## Context

The engineering backlog’s **C-18** is “pgvector → Qdrant migration”. KerrOS never
shipped a live pgvector primary store — RAG is SQLite FTS5 (`rag/store.py`) with
an optional `QdrantVectorStore` behind `HybridMemoryAdapter`. C-18 was deferred
until a rented-server / RAG-scale trigger. Operators now want a reproducible
Qdrant sidecar, health probe, and SQLite→Qdrant backfill without abandoning FTS.

## Decision

Treat C-18 as **optional Qdrant ops foundation**, not a cutover:

1. Keep **SQLite FTS as primary** MemoryPort keyword path
2. Harden `QdrantVectorStore` — UUID point IDs, `probe_qdrant()`, `indices=` upsert
3. **`deploy/qdrant/`** — official image, loopback `127.0.0.1:6333`, named volume
4. **`scripts/migrate_sqlite_rag_to_qdrant.py`** — batch backfill from `chunks`
5. Wire `components.qdrant` into `HealthMonitor` (fail overall only if enabled+down)
6. Collection naming remains P5-guarded (`kerros_memory`; reject OmniRoute names)

“pgvector → Qdrant” in the backlog means *scale path for vectors*, not a
Postgres dump.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Make Qdrant primary now | Breaks Termux / offline default; FTS still required |
| Stand up Postgres+pgvector first | Extra ops; no current pgvector runtime |
| Share OmniRoute vectors | Violates MEMORY_SEPARATION |

## Consequences

**Positive:** Operators can `qdrant_docker.sh up` + migrate; hybrid recall has a
supported sidecar; CI covers mocked HTTP + compose loopback.

**Negative:** Dual-write on upsert (SQLite + Qdrant) can drift if Qdrant is down;
migration is best-effort backfill, not a transaction.

## Revisit when

Vector recall becomes the default ranking path or chunk volume makes SQLite FTS
insufficient — then evaluate primary-store cutover and re-chunking (ADR-002).
