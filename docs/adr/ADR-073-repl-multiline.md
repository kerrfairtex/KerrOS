# ADR-073: REPL Multiline Continuation

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-067 added history and slash autocomplete. Operators still need a light
multiline path for pasting short scripts / tool payloads without moving to
a full-screen TUI.

## Decision

1. Treat a trailing `\` as a line-continuation marker in `prompt_line`.
2. Join continued physical lines with newlines.
3. Default on; disable with `KERROS_REPL_MULTILINE=0`.
4. Keep Enter = submit for non-continued lines (no Alt+Enter surprise).

## Consequences

**Positive:** Paste-friendly Soft scripts in the brand REPL.

**Negative:** Not a full multiline editor; TUI remains deferred.

## Revisit when

A full-screen desktop TUI application is funded.
