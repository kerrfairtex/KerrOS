# ADR-087: Persisted Channel/TUI Trace

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-083 TUI traces were memory-only. Channel bridges needed a durable Soft
event log for operators.

## Decision

1. Add **`gateway/channels/trace.py`** JSONL store at
   `data/channel_trace.jsonl` (capped).
2. Channel tool agent + TUI append events.
3. Expose `gateway channel trace`.

## Consequences

**Positive:** Cross-session Soft observability.

**Negative:** Not a full SIEM; local file only.

## Revisit when

SIEM export or redaction policies are required.
