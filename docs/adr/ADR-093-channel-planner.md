# ADR-093: Soft Planner Channel Agent

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-090 tool loops are single-thread detect chains. Operators want a Soft
plan splitter (`then` / `;` / newlines) that runs each step through
tools or Soft/LLM reply.

## Decision

1. Add **`gateway/channels/planner_agent.py`**.
2. Expose `gateway channel plan-reply` (`KERROS_CHANNEL_PLANNER=0` disables).

## Consequences

**Positive:** Multi-step Soft messaging plans without a heavy planner.

**Negative:** Heuristic split only — not LLM-generated DAGs.

## Revisit when

LLM-authored structured plans are funded.
