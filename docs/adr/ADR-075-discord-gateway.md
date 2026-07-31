# ADR-075: Discord Gateway Soft + Optional Live Websocket

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-069 Discord REST covers send/poll for a fixed channel. Presence-quality
ingress still needs Gateway DISPATCH events (MESSAGE_CREATE) without forcing
a websocket dependency in CI.

## Decision

1. Add **`gateway/channels/discord_gateway.py`** Soft event bus.
2. Inject Soft events via `soft_dispatch` /
   `gateway channel gateway-dispatch MESSAGE_CREATE <json>`.
3. Live websocket behind `KERROS_DISCORD_GATEWAY_LIVE=1` + token when
   `websocket-client` is installed; otherwise Soft with a clear status note.
4. `poll_all` drains Gateway inbox alongside adapter polls.

## Consequences

**Positive:** CI-complete Gateway path; optional live without new hard deps.

**Negative:** Intents/presence/slash commands remain deferred.

## Revisit when

Slash interactions or multi-shard Gateway orchestration is funded.
