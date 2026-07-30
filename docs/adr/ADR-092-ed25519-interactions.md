# ADR-092: Optional Ed25519 Interactions Verify

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-084 Soft HMAC is CI-safe but not Discord-compatible. Operators with
PyNaCl can verify real Ed25519 signatures.

## Decision

1. When `KERROS_DISCORD_INTERACTIONS_SOFT=0`, verify via PyNaCl
   `VerifyKey` using hex `KERROS_DISCORD_PUBLIC_KEY`.
2. Soft HMAC remains the default path.

## Consequences

**Positive:** Optional live Discord Interactions compatibility.

**Negative:** PyNaCl is an optional dependency (not required in core).

## Revisit when

Bundling a vetted crypto dependency in core requirements is accepted.
