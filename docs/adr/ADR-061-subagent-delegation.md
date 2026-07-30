# ADR-061: Subagent Delegation (RAM-aware, default-off)

**Status:** Accepted  
**Date:** 2026-07-30  
**Supersedes:** deferred-only note in prior ADR-061 draft

## Context

Hermes can spawn concurrent child agents for independent workstreams.
KerrOS agents were serialized through the REPL. We re-implement the
*behavior* natively (no Hermes clone): capped parallelism, restricted
agent set, inherited tool gating.

Dev hosts may have ample RAM; phones may not. Capability must be
**device-aware**, not assumed from any cloud IDE VM size.

## Decision

1. Add **`agents/subagents.py`** with `delegate_tasks`.
2. Default **off** (`KERROS_SUBAGENTS=1` to enable).
3. Max workers **2**; drop to **1** or **0** based on `MemAvailable`
   (`>=2048 MiB` → up to 2; `>=1024` → 1; else refuse).
4. Allowlisted child agents only: `knowledge`, `research`, `code`, `react`
   (not unrestricted security/deploy surfaces).
5. Expose router tool / CLI: `delegate …` / `/delegate`.
6. Results converge into a text summary for the parent turn.

Out of scope: Hermes messaging gateway, 3-way concurrency, cloning Hermes.

## Consequences

**Positive:** Parallel research/code/knowledge work when enabled and safe.

**Negative:** Unknown `/proc` RAM falls back to 1 worker; disabled by default.

## Revisit when

Planner emits structured parallel plans automatically, or sandbox-per-child
terminal backends are funded.
