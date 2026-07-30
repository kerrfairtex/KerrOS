# ADR-091: Signal Soft HTTP Relay

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-076 live Signal depends on a local `signal-cli`. Hosted bridges need a
Soft HTTP ingest that does not embed the daemon in KerrOS.

## Decision

1. Add **`gateway/channels/signal_relay.py`** Soft ingest.
2. Expose `POST /v1/signal` on the gateway and
   `gateway channel signal-ingest <json>`.

## Consequences

**Positive:** Decoupled Soft Signal ingress for external daemons.

**Negative:** Auth is shared gateway token only.

## Revisit when

Signed per-bridge credentials are funded.
