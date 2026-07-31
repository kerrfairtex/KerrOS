# ADR-071: Signal Soft Channel Adapter

**Status:** Accepted  
**Date:** 2026-07-30

## Context

WhatsApp Soft (ADR-070) completed the messaging Soft matrix except Signal.
Operators want the same KerrOS channel protocol available for Signal demos
and CI without a live daemon dependency.

## Decision

1. Add **`gateway/channels/signal.py`** Soft adapter with the standard
   `start` / `stop` / `poll` / `send` / `soft_push` surface.
2. Enable with `KERROS_SIGNAL=1`; register as `signal`.
3. Live `signal-cli` (or equivalent) bridge stays deferred behind a future
   `KERROS_SIGNAL_LIVE` flag.

## Consequences

**Positive:** Full Soft channel set for Telegram / Discord / WhatsApp / Signal.

**Negative:** No live Signal transport in this build.

## Revisit when

A local signal-cli daemon bridge or desktop TUI session bridge is funded.
