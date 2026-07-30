# ADR-062: Agent Capability Expansion

**Status:** Accepted  
**Date:** 2026-07-30

## Context

KerrOS already had progressive skills, session FTS, tool hooks, pipelines, and
subagent delegation (ADR-056…061), but several agent-runtime surfaces remained
thin: durable profile memory, progressive tool disclosure, dangerous-exec
approval beyond scope gates, persisted agent cron jobs, and a soft MCP bridge.
Operators also needed a larger curated skill library under `skills/`.

## Decision

1. **`memory/profile_store.py`** — `MEMORY.md` / `USER.md` under `data/memories/`
   with §-delimited entries, char budgets, frozen session snapshot, and
   `profile_memory` router tool.
2. **`tools/tool_search.py`** — progressive disclosure helpers
   (`tool_search` / `tool_describe`); enable with `KERROS_TOOL_SEARCH=1`.
3. **`tools/exec_approval.py`** — dangerous-command pre-hook for shell-like
   tools; session allow via `approve exec` / `KERROS_EXEC_APPROVE=1`.
4. **`runtime/agent_jobs.py` + `tools/agent_cron.py`** — persisted cron jobs in
   `data/agent_cron/jobs.json` using KerrOS `runtime.cron`.
5. **`adapters/mcp/bridge.py`** — soft MCP discovery (default-off;
   `KERROS_MCP=1`); live RPC gated by `KERROS_MCP_LIVE=1`.
6. Expand **`skills/`** with scrubbed community skill markdown (KerrOS naming).

Out of scope for this ADR: messaging channel gateway, full live MCP transports,
desktop TUI.

## Consequences

**Positive:** Closes major agent-runtime gaps while preserving fail-closed
scope gates and Soft/Fake defaults for CI.

**Negative:** Skill corpus is large; agents should use `skills_list` /
`skill_view` rather than loading everything.

## Revisit when

Live MCP transport, channel gateway, or richer context compression is funded.
