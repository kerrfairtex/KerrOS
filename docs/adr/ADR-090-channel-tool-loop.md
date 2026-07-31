# ADR-090: Multi-Step Soft Channel Tool Loop

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-085 runs a single tool. Some Soft demos need a short detect→run→detect
chain without a full planner.

## Decision

1. Add **`gateway/channels/tool_loop.py`** with capped steps
   (`KERROS_CHANNEL_TOOL_STEPS`, default 3, max 6).
2. Expose `gateway channel tool-loop`.
3. Deploy tools remain blocked; falls back to Soft/LLM when no tools match.

## Consequences

**Positive:** Short Soft tool chains on messaging bridges.

**Negative:** Not a full ReAct planner.

## Revisit when

Planner-backed channel agents are funded.
