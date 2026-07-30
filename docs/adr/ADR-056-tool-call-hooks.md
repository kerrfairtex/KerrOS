# ADR-056: Tool Call Pre/Post Hooks

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Hermes Agent wraps every tool invocation with `pre_tool_call` /
`post_tool_call` hooks so approval, logging, and metrics can plug in
without editing the dispatcher. KerrOS already fail-closes via
`tools/scope_gate.py` inside `kernel/router.run_tool`, but there is no
general hook registry — every new cross-cutting concern would otherwise
patch `router.py` again.

## Decision

1. Add **`tools/tool_hooks.py`** with `register_pre_tool_call` /
   `register_post_tool_call` and runners that never print secrets.
2. Wire hooks in **`kernel/router.run_tool`**: run all pre-hooks before
   dispatch; run post-hooks after (including on gated deny).
3. Register **`scope_gate.check` as the first pre-hook** so fail-closed
   gating remains the same behavior, now expressed as a hook.
4. Keep CLI interactive authorize/arm UX that calls `scope_gate` before
   `run_tool` unchanged (double-check is intentional).

Out of scope: Hermes approval UI callbacks, remote policy servers.

## Consequences

**Positive:** Logging/metrics/future gates plug in without touching
dispatch tables.

**Negative:** Misbehaving pre-hooks can block tools — hooks must be
fail-safe (exceptions → deny with reason).

## Revisit when

A funded deploy needs async approval callbacks or per-tool rate limits.
