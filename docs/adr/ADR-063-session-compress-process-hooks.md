# ADR-063: Session Store, Compression, Processes, Lifecycle Hooks

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-058–062 delivered flat session FTS, message alternation, profile memory,
tool search, exec guards, agent cron, soft MCP, and subagents. Remaining gaps
for a production agent runtime: session-scoped recall/browse, deeper context
compression, background process tracking with interrupt, session lifecycle
hooks, and optional live HTTP MCP calls.

## Decision

1. **`memory/session_store.py`** — SQLite sessions + turns + FTS; `list_sessions`,
   `browse_session`, `search_sessions`; wired from `memory.manager.add_message`.
2. **`core/context_compressor.py`** — prune tool blobs, structured extractive
   fold, Soft LLM summarize behind `KERROS_LLM_COMPRESS=1`; used from REPL when
   history crosses the 50% window.
3. **`tools/process_registry.py` + `tools/interrupt.py`** — background spawn /
   poll / wait / kill with per-thread interrupt; CLI/router `bg …`.
4. **`core/session_hooks.py`** — `session_start|end` / `turn_start|end` hooks.
5. **MCP HTTP live path** — `KERROS_MCP_LIVE=1` enables JSON-RPC `tools/list` /
   `tools/call` against configured server `url` (stdio still Soft).

## Consequences

**Positive:** Cross-session browse/search with session ids; safer long jobs;
cleaner long-chat context on small models.

**Negative:** Background `shell=True` spawn is still gated by exec approval /
scope policies for interactive tools; operators must not disable guards.

## Revisit when

Messaging channel gateway or sandbox-backed process backends are funded.
