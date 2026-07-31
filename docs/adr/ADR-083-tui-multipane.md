# ADR-083: TUI Multi-Pane Status/Trace

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-078 shipped a single conversation pane. Operators asked for a status /
trace side pane without a desktop GUI.

## Decision

1. Extend **`cli/tui.py`** with a right-hand status/trace pane (VSplit).
2. Add `/trace` and `/status` Soft commands; log user/assistant events.

## Consequences

**Positive:** Full-screen Soft session with operational visibility.

**Negative:** Trace is local buffer only (not persisted).

## Revisit when

Persisted tool/trace timelines or mouse-driven layouts are required.
