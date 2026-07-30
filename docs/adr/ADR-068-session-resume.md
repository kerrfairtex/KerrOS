# ADR-068: Session Resume into REPL

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-063 indexed chat sessions for list/browse/FTS. Operators still needed a
modern-agent-CLI path to **continue** a past session in the live REPL
(`/resume`), not only inspect it.

## Decision

1. Add **`resume_session`** / **`format_resume_picker`** on `memory.manager`.
2. Load turns into short-term memory without re-indexing; switch
   `session_store` current id so new turns append to the resumed session.
3. Expose `/resume` (picker), `/resume <id>`, `/resume latest` in the REPL
   and via `detect_tool` (`resume session …`).

## Consequences

**Positive:** Continuity across restarts; matches expected agent-CLI UX.

**Negative:** Resume loads extractive history only (no fork/branch yet).

## Revisit when

Interactive picker UI or session fork/branch is required.
