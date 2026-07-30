# ADR-060: Execute-Pipeline Tool Collapsing

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Hermes collapses fixed multi-step tool sequences into one sandboxed script
so the LLM is not invoked at every mechanical step. KerrOS already has
`code_saver.run_and_verify` and scope gates, but no allowlisted
tool-RPC pipeline runner.

## Decision

1. Add **`tools/pipeline_exec.py`** — subprocess runner with `call(tool, args)`
   bound to `kernel.router.run_tool` (hooks + scope_gate apply).
2. Allowlist only passive tools (`calc`, `sysinfo`, `search_past_sessions`, …).
   Offensive/deploy tools stay out of pipelines.
3. Block `os.system` / `subprocess` / `open` / `eval` in scripts.
4. Expose as router tool `execute_pipeline`.

## Consequences

**Positive:** Token savings on fixed sequences; gates still apply per call.

**Negative:** Allowlist is intentionally small until trusted.

## Revisit when

Planner Agent can mark a plan as “mechanical-only” and emit a pipeline.
