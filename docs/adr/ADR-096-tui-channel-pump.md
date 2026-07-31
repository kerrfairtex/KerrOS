# ADR-096: TUI Channel Inbox Pump Command

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-083 TUI was conversation-only. Operators want to Soft-trigger channel
registry actions (`soft-reply`, `pump`, `trace`) from the TUI.

## Decision

1. Add `/channel [action …]` in `cli/tui.py` calling `channels_cmd`.
2. Default action: `soft-reply`.

## Consequences

**Positive:** Full-screen Soft ops without leaving the TUI.

**Negative:** Output truncated to a short snippet in-pane.

## Revisit when

Dedicated channel ops pane is funded.
