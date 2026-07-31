# ADR-074: LLM-Backed Channel Bridge

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-072 Soft-acks inbound channel messages without an LLM. Operators need an
opt-in path that calls KerrOS `generate_complete` while keeping Soft fallback
for CI and offline hosts.

## Decision

1. Add **`gateway/channels/bridge.py`** with `llm_reply_once` /
   `generate_channel_reply` / `bind_channel_engine`.
2. Enable with `KERROS_CHANNEL_LLM=1`; expose `gateway channel llm-reply`.
3. On missing engine or generation failure, fall back to Soft ack text.

## Consequences

**Positive:** End-to-end messaging → LLM → outbound without custom glue.

**Negative:** No per-channel persona routing yet.

## Revisit when

Streaming channel replies or tool-using channel agents are required.
