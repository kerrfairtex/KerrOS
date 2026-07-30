# ADR-069: Discord Soft Deepen + Optional Live REST

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-066 shipped a Discord Soft skeleton (inbox/outbox only). Telegram already
had optional live Bot API. Operators need Discord Soft parity plus an
opt-in REST path without taking on the full Gateway websocket stack.

## Decision

1. Deepen **`DiscordAdapter`** Soft counters/status to match Telegram Soft.
2. Enable live Bot **REST** behind `KERROS_DISCORD_LIVE=1` +
   `KERROS_DISCORD_TOKEN` (+ optional `KERROS_DISCORD_CHANNEL` default).
3. Live `poll` uses `GET /channels/{id}/messages?after=…`; `send` uses
   `POST /channels/{id}/messages`. Soft remains the default.
4. Full Discord Gateway websocket stays out of scope.

## Consequences

**Positive:** Soft CI demos + optional live send/poll without new deps.

**Negative:** No presence, reactions, or gateway events until a later ADR.

## Revisit when

Gateway websocket, slash-command interactions, or multi-guild routing is required.
