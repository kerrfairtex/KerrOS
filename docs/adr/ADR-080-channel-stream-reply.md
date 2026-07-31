# ADR-080: Soft Streaming Channel Replies

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-074 returns a single final reply. Operators want Soft progressive chunks
for demos and an injectable stream path before committing to live token
streaming on every platform.

## Decision

1. Add `iter_channel_reply_chunks` + `stream_reply_once`.
2. Soft mode chunks the final text; optional `stream_fn` for LLM tokens.
3. Expose `gateway channel stream-reply` (`KERROS_CHANNEL_STREAM=0` disables
   Soft chunking, still sends final).

## Consequences

**Positive:** Stream-shaped Soft demos without platform edit/message APIs.

**Negative:** One outbound send of the final text (no live edit-in-place).

## Revisit when

Platform-native progressive edits are funded.
