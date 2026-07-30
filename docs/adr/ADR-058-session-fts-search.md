# ADR-058: FTS5 Past-Session Search

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Operators need full-text recall across past chat sessions, ideally with
optional summarization. KerrOS RAG already uses FTS5 (`rag/store.py`), but
chat history lives in `data/memory.json` with only recent-window helpers —
no full-text cross-session recall tool.

## Decision

1. Add **`memory/session_fts.py`** — SQLite FTS5 index at
   `data/session_fts.db`, synced from `add_message` / bulk import of
   `memory.json`.
2. Add router tool **`search_past_sessions`** (read-only, not offensive).
3. Optional short extractive summary (no extra LLM required by default);
   LLM summarize stays Soft behind a flag later.
4. Paths stay under KerrOS `data/` (MEMORY_SEPARATION).

## Consequences

**Positive:** “What did we decide about X?” works without re-reading JSON.

**Negative:** Index can lag if messages are written outside `add_message`.

## Revisit when

Episodes and reflections should join the same FTS corpus.
