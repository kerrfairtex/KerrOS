# ADR-084: Soft Discord Interactions HTTP Endpoint

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-081 Soft slash handlers lacked an HTTP surface Discord (or a local
bridge) can POST to. Live Ed25519 verification needs crypto deps.

## Decision

1. Add `POST /v1/interactions` on the KerrOS gateway.
2. Soft-verify signatures via HMAC-SHA256 over `timestamp+body` using
   `KERROS_DISCORD_PUBLIC_KEY` (`KERROS_DISCORD_INTERACTIONS_SOFT=1` default).
3. PING → `{type:1}`; APPLICATION_COMMAND → slash Soft handlers.

## Consequences

**Positive:** CI-complete Interactions path without PyNaCl.

**Negative:** Soft HMAC is not Discord-compatible Ed25519.

## Revisit when

PyNaCl/ed25519 live verify is funded.
