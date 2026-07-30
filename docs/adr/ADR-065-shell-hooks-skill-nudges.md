# ADR-065: Shell Hooks, Skill Self-Improve, Memory Nudges

**Status:** Accepted  
**Date:** 2026-07-30

## Context

With ADR-061–064 in place, KerrOS still lacked: (1) operator-defined shell
scripts on tool/session lifecycle events, (2) lightweight skill improvement
when skills are used, (3) periodic nudges to persist memory/skills.

## Decision

1. **`tools/shell_hooks.py`** — config-driven shell hooks (`KERROS_SHELL_HOOKS=1`),
   workspace-bound argv, optional JSON block on pre_tool.
2. **`tools/skill_improve.py`** — usage stats + optional Lessons append
   (`KERROS_SKILL_IMPROVE=1`) when skills are recorded as used.
3. **`memory/nudges.py`** — turn counters; inject soft reminders when
   `KERROS_MEMORY_NUDGES=1`.

## Consequences

**Positive:** Operators can extend policy without patching router; skills and
memory keep improving across sessions.

**Negative:** Shell hooks can deny tools — keep scripts reviewed and under
workspace only.

## Revisit when

Full plugin manager / marketplace hooks are funded.
