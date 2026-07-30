# ADR-095: Soft Channel Rate Limits

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Messaging bridges can Soft-flood session indexes. Operators need a simple
in-process rate limit.

## Decision

1. Add **`gateway/channels/rate_limit.py`** sliding window
   (`KERROS_CHANNEL_RATE=30/60`).
2. Enforce on Soft reply loop (ADR-072 path).

## Consequences

**Positive:** Soft abuse guard for demos/CI floods.

**Negative:** Process-local only (not distributed).

## Revisit when

Redis/shared rate stores are funded.
