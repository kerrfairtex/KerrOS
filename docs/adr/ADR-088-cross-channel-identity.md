# ADR-088: Cross-Channel Soft Identity Linking

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Per-channel session routing (ADR-079) isolated threads. Operators still need
optional Soft links so the same human on Telegram and Discord can share a
routed identity key.

## Decision

1. Add **`gateway/channels/identity.py`** JSON store of aliases → identity id.
2. `gateway channel identity link|unlink|resolve|list`.
3. `session_id_for` uses `routed_sender` when a link exists.

## Consequences

**Positive:** Soft cross-channel continuity without OAuth.

**Negative:** Manual link management only.

## Revisit when

Verified account linking (OAuth / phone proof) is funded.
