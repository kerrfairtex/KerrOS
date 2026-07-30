# ADR-081: Discord Slash Soft Interactions

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-075 Gateway Soft handles MESSAGE_CREATE. Slash commands need the same
Soft path without a public Interactions HTTP endpoint.

## Decision

1. Add **`gateway/channels/slash.py`** with Soft handlers:
   `/ping` `/help` `/status` `/resume-hint`.
2. `gateway channel slash <name> [json]` and Gateway
   `INTERACTION_CREATE` Soft dispatch share handlers.

## Consequences

**Positive:** CI-complete slash demos; resume routing hints.

**Negative:** No live Discord Interactions signature verify yet.

## Revisit when

Public Interactions HTTP + signature verification is funded.
