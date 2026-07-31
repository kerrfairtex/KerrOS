# ADR-099: TUI Dedicated Channel Ops Pane

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-096 `/channel` dumped into the conversation pane. Operators want a
dedicated Soft ops pane for channel actions.

## Decision

1. Add a right-hand **CHANNEL OPS** pane in `cli/tui.py`.
2. `/channel …` records snippets there; `/ops` toggles visibility flag
   (layout keeps pane; Soft status notes toggle).

## Consequences

**Positive:** Full-screen Soft channel operations visibility.

**Negative:** Layout does not hot-rebuild on `/ops` in this build.

## Revisit when

Dynamic layout rebuild / mouse panes are funded.
