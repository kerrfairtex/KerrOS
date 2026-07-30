# ADR-066: Messaging Channel Adapters

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-064 delivered a loopback HTTP webhook ingress. Operators still need
first-class channel adapters so Telegram (and later Discord) can feed the
same inbox without custom glue for every deploy.

## Decision

1. Add **`gateway/channels/`** with a small adapter protocol
   (`start` / `stop` / `poll` / `send`).
2. Ship **Telegram** Soft-by-default; live Bot API behind
   `KERROS_TELEGRAM_LIVE=1` + `KERROS_TELEGRAM_TOKEN`.
3. Ship **Discord** Soft skeleton (live REST deepened in ADR-069; no Gateway websocket).
4. Expose via `gateway channel …` (list/start/stop/pump/send/soft-push).
5. `pump` copies polled messages into the webhook inbox for unified handling.

## Consequences

**Positive:** One KerrOS inbox model for HTTP + chat platforms.

**Negative:** Discord Gateway websocket and other platforms remain deferred (see ADR-069 for REST).

## Revisit when

WhatsApp/Signal adapters or a full desktop TUI session bridge is required.
