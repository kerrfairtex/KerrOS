# ADR-102: Soft Progressive Message Edits

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-080 Soft-streams chunks but sends only a final message. Operators want
Soft progressive edit records (and live edit APIs when available).

## Decision

1. Add **`stream_edit_reply_once`** + adapter `soft_edit` on Telegram/Discord.
2. Expose `gateway channel stream-edit`.

## Consequences

**Positive:** Stream-shaped Soft demos with edit timelines.

**Negative:** Soft message ids are local until a live send returns a real id.

## Revisit when

Live create-then-edit flows are funded end-to-end.
