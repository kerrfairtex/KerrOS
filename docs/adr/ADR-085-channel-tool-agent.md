# ADR-085: Soft Tool-Using Channel Agent

**Status:** Accepted  
**Date:** 2026-07-30

## Context

LLM channel replies cannot invoke KerrOS tools. Operators want inbound
messages that match `detect_tool` to run Soft-safe tools before falling
back to Soft/LLM text.

## Decision

1. Add **`gateway/channels/tool_agent.py`** with `tool_reply_once`.
2. Block deploy/self_run tools on the messaging path.
3. Expose `gateway channel tool-reply` (`KERROS_CHANNEL_TOOLS=0` disables).

## Consequences

**Positive:** Messaging → tool → outbound Soft demos.

**Negative:** No multi-step tool loops yet.

## Revisit when

Multi-step channel tool agents are funded.
