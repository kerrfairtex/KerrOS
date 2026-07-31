# ADR-079: Per-Channel Session Routing

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Soft/LLM channel bridges indexed turns into the global REPL session, mixing
Telegram/Discord/WhatsApp threads. Operators need isolated session ids per
`(channel, chat_id, sender)`.

## Decision

1. Add **`gateway/channels/routing.py`** with stable `session_id_for` /
   `index_channel_turn`.
2. Default on (`KERROS_CHANNEL_ROUTING=0` disables).
3. Wire Soft reply + LLM/stream bridges to use routed sessions.

## Consequences

**Positive:** Clean `/resume ch-…` continuity per chat thread.

**Negative:** Does not migrate historical unrouted turns.

## Revisit when

Cross-channel identity linking is required.
