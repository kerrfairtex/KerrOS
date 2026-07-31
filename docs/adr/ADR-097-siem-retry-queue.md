# ADR-097: Soft SIEM Push Retry/Backoff Queue

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-094 live SIEM push fails hard on network errors. Operators need a Soft
durable retry queue with exponential backoff.

## Decision

1. Add **`gateway/channels/siem_queue.py`** JSONL queue.
2. Failed `push_trace` enqueues payloads; `gateway channel siem-flush` drains.
3. Cap attempts at 8 with backoff up to 300s.

## Consequences

**Positive:** Soft-resilient SIEM delivery across restarts.

**Negative:** Local file queue only.

## Revisit when

Multi-node shared queues are funded.
