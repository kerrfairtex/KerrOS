# ADR-094: Soft Live SIEM HTTP Push

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-089 exported files. Operators want Soft live POST of JSON/CEF batches
to a collector URL.

## Decision

1. Add **`gateway/channels/siem_push.py`**.
2. Enable with `KERROS_SIEM_PUSH=1` + `KERROS_SIEM_URL` (+ optional token).
3. Expose `gateway channel siem-push [json|cef]`.

## Consequences

**Positive:** Soft live SIEM handoff without vendors.

**Negative:** Best-effort HTTP only; no retry queue yet.

## Revisit when

Durable retry/backoff queues are funded.
