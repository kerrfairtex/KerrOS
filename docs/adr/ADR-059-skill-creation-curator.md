# ADR-059: Skill Creation from Experience + Curator

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Hermes writes reusable Markdown skills after complex successful tasks and
curates overlap/staleness. KerrOS already has progressive-disclosure skills
(ADR-007) via `skill_manage`, but no automatic episode→skill trigger.

## Decision

1. Track tool-call counts via post-hook `skill_experience` (ADR-056).
2. After ≥5 successful tool calls in an episode, auto-write
   `skills/learned/auto_*.md` (not always injected into context).
3. Add `skills_curate` tool / `skills curate` command to dedupe and archive
   unpinned stale learned skills.
4. Pinned skills (`kerros:pinned=true`) are never archived.

## Consequences

**Positive:** Procedures accumulate without bloating always-on memory.

**Negative:** Auto skills may be noisy — curator + pin flag required.

## Revisit when

Reflection Agent should attach `tool_call_count` onto episodic records.
