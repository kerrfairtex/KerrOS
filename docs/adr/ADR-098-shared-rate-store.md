# ADR-098: File-Backed Soft Shared Rate Store

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-095 rate limits are process-local. Multiple KerrOS processes need Soft
shared counters without Redis.

## Decision

1. Persist hits under `data/channel_rate.json` when
   `KERROS_CHANNEL_RATE_SHARED=1`.
2. Keep in-memory default for CI speed.

## Consequences

**Positive:** Soft multi-process rate sharing.

**Negative:** Not strongly consistent under concurrent writers.

## Revisit when

Redis/shared stores are funded.
