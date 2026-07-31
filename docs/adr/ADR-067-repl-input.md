# ADR-067: Professional REPL Input (history + slash autocomplete)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

KerrOS chat used bare `input()`. Operators expect modern agent-REPL UX:
persistent history and slash-command autocomplete without abandoning the
angel/sword brand chrome.

## Decision

1. Add **`cli/repl_input.py`** wrapping `prompt_toolkit` when a TTY is
   present (`KERROS_REPL_PT=0` forces plain input).
2. Persist history at `data/repl_history`.
3. Autocomplete core `/…` commands plus frequent natural tool phrases.
4. Keep brand prompt rendering via ANSI in `cli/ui.prompt_input`.

## Consequences

**Positive:** Faster command discovery; session continuity across restarts.

**Negative:** Optional dependency — falls back cleanly when unavailable.

## Revisit when

A full-screen TUI application (separate process) is funded. Light multiline
continuation shipped in ADR-073.
