# ADR-078: Light Full-Screen TUI Shell

**Status:** Accepted  
**Date:** 2026-07-30

## Context

The line REPL (ADR-067/073) is the default. Operators asked for a full-screen
terminal session bridge without abandoning KerrOS brand chrome or requiring
a desktop GUI toolkit.

## Decision

1. Add **`cli/tui.py`** using `prompt_toolkit` Application (conversation pane
   + input bar).
2. Soft-echo by default; optional `--llm` / `KERROS_TUI_LLM=1` binds
   `AdaptiveEngine` when available.
3. Launch: `python3 -m cli.tui`.

## Consequences

**Positive:** Full-screen Soft session without a separate desktop app.

**Negative:** Not a rich multi-pane IDE; brand splash stays on line REPL boot.

## Revisit when

Multi-pane tool/trace views or mouse-driven layouts are required.
