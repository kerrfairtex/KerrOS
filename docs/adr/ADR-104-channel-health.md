# ADR-104: Soft Channel Health Probes

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Operators need a single Soft health snapshot across adapters, Discord Gateway,
SIEM queue, and traces.

## Decision

1. Add **`gateway/channels/health.py`** `probe_channels`.
2. Expose `gateway channel health`.

## Consequences

**Positive:** Soft ops visibility in one call.

**Negative:** Soft status only — not deep live API pings by default.

## Revisit when

Live latency SLOs per channel are funded.
