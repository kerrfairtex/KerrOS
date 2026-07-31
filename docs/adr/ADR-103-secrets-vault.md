# ADR-103: Soft Secrets Vault File

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Bridge/WABA/SIEM secrets clutter env files. Operators need a Soft local vault
with best-effort file mode lockdown.

## Decision

1. Add **`gateway/channels/secrets.py`** at `data/channel_secrets.json`.
2. Expose `gateway channel secret list|set|get|delete|apply`.
3. `get` never prints values — only presence/length.

## Consequences

**Positive:** Soft local secret hygiene for demos.

**Negative:** Not a hardware HSM / OS keychain.

## Revisit when

OS keyring integration is funded.
