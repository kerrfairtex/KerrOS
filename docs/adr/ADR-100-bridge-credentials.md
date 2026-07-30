# ADR-100: Soft Signed Bridge Credentials

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-091 Signal HTTP relay shared only the gateway token. Hosted bridges need
per-bridge Soft HMAC credentials.

## Decision

1. Add **`gateway/channels/bridge_auth.py`**.
2. Enable with `KERROS_BRIDGE_AUTH=1` + `KERROS_BRIDGE_SECRETS` JSON map.
3. Require `X-Kerros-Bridge-Id|Ts|Sign` on `/v1/signal` when enabled.

## Consequences

**Positive:** Soft per-bridge auth without OAuth.

**Negative:** Secrets still env-file based.

## Revisit when

A credential vault is funded.
