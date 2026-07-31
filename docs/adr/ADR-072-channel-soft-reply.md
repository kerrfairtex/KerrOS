# ADR-072: Soft Channel Reply Loop

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Channel adapters can Soft-push and pump into the webhook inbox, but demos
still needed a one-shot Soft reply path that proves end-to-end ingress →
ack → session index without requiring an LLM or live network.

## Decision

1. Add **`soft_reply_once`** on the channel registry.
2. Expose as `gateway channel soft-reply` (alias `reply-once`).
3. Behavior: poll running adapters → webhook inbox → index user/assistant
   turns in `session_store` → Soft `send` ack per inbound.
4. No LLM call in this path; keep CI deterministic.

## Consequences

**Positive:** Full Soft round-trip for Telegram/Discord/WhatsApp/Signal demos.

**Negative:** Acks are template text only until an LLM-backed channel bridge.

## Revisit when

Live LLM channel bridge or per-channel session routing is funded.
