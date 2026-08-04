# ADR-106: Unified Multi-Agent Memory (Default On)

**Status:** Accepted  
**Date:** 2026-08-04

## Context

KerrOS already has chat JSON, profile MD, semantic/episodic, session FTS, and
RAG MemoryPort layers. Operators need a **first-class agent memory** that is
on by default: Scout-style persistence (preferences, contacts, drafts, tasks,
account context), shareable across agents, scoped read/write attach, optimistic
concurrency, versioning with session attribution, a portable manage/export API,
periodic “dreaming” curation, plus bash + memory-graph tools.

RAG MemoryPort stays separate (`docs/MEMORY_SEPARATION.md`).

## Decision

1. Add **`memory/unified_store.py`** under `data/agent_memory/` with named
   stores (`org` read-only, `team` / `scout` read-write by default).
2. **Memory ON by default** via `kernel.config` `kerros_memory.enabled=True`.
3. Writes require optional **`expected_sha256`**; mismatches return conflict
   (no silent overwrite). Every write versions content and attributes
   `session_id` / `agent`.
4. Sessions **attach** one or more stores with access levels; prompt injection
   reads attached snapshots.
5. Seed a **Scout inbox** layout (`notes/`, `email_draft/`, `task/`) with
   developer-customizable defaults.
6. Soft **dreaming** (`memory/dreaming.py`) batch-organizes recent transcripts
   into stores (heuristic by default; optional LLM).
7. Portable **`memory/manage.py`** export/import/list API + router tools
   `kerros_memory` and `memory_graph`. Keep **bash** as the shell tool.

## Alternatives considered

- Extend only `profile_store` — rejected: no scopes, versions, or multi-agent attach.
- Promote `task_assistant/memory_store.py` as production — rejected: prototype
  (mtime note only); patterns ported into KerrOS instead.
- Single global SQLite blob — rejected: markdown files stay inspectable and
  developer-editable; SQLite reserved for session_store / RAG.

## Consequences

**Positive:** Multi-agent shared learning with safe concurrent writes; Scout
inbox memory usable without a cloud portal; audit trail via versions.

**Negative:** Another on-disk tree beside `data/memories/`; operators must not
confuse agent memory with RAG MemoryPort.

## Revisit when

A single backend (SQLite/object store) is required for HA multi-host agents, or
org-policy mandates encrypted-at-rest agent memory.
