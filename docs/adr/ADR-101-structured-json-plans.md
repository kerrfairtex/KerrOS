# ADR-101: Soft Structured JSON Channel Plans

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-093 heuristic `then` splitting is weak for authored plans. Operators want
JSON `{"steps":[…]}` Soft plans (optional LLM-authored JSON).

## Decision

1. Add **`gateway/channels/structured_plan.py`**.
2. Expose `gateway channel json-plan`.
3. Parse JSON steps or Soft-generate via bound LLM; fallback to splitter.

## Consequences

**Positive:** Deterministic Soft multi-step messaging plans.

**Negative:** LLM JSON authoring is best-effort Soft.

## Revisit when

Strict schema validation / DAG plans are funded.
