# ADR-007: Hermes-style Progressive Disclosure Skill System

**Status:** Accepted  
**Date:** 2026-07-25  
**Deciders:** KerrOS engineering

## Context

As KerrOS matures, the complexity and quantity of system guidelines, coding templates, architectural patterns, and tool capabilities increase. 
Surfacing all of these detailed instructions (Level 1) to LLM agents at the beginning of every session would be highly inefficient. It would incur significant input token overhead (thousands of tokens per user message/turn) and cause context dilution, reducing agent instruction-following performance.
Conversely, leaving the agent completely unaware of available skills, capabilities, and system guidelines makes it blind, limiting its ability to discover and invoke required specialized guides or tool catalogs.
Furthermore, as KerrOS is a self-evolving system, agents need a mechanism to systematically persist newly discovered patterns, workflows, and tools as reusable skills for future turns or sessions.

## Decision

Implement a Hermes-style Progressive Disclosure Skill System comprising three distinct levels of architecture to balance orientation and token efficiency:

1. **Level 0 (Low-Cost Indexing) — `skills_list()`**:
   Surfaces a compact, structured catalog index of all available skills at session start. It groups skills by category (e.g., `web_stack`, `ai_patterns`, and `tool_catalog`), providing only the skill name and a brief one-line description. This minimal footprint (~3k tokens) avoids context bloat while keeping the agent oriented.
2. **Level 1 (On-Demand Retrieval) — `skill_view()`**:
   Loads and returns the full markdown content of a specific skill or tool catalog by name, or via an explicit path relative to the workspace. This keeps the detailed guidance zero-cost until actually requested by the agent.
3. **Level 2 (Dynamic Capability Evolution) — `skill_manage()`**:
   Allows agents to write, update, or delete their own custom markdown skills under `<WORKSPACE>/skills/<category>/<name>.md`. This facilitates self-evolution, allowing agents to persist newly discovered workflows or patterns as reusable skills.

### Architectural Features

- **Skill Storage**: Native skills are stored in the workspace under `skills/<category>/<name>.md`.
- **Automatic Metadata Extraction**: The first line beginning with `#` is parsed as the title; the next non-blank line is used as the short description in the compact index.
- **Unified Cataloging**: Curated YAML tool definitions from `tools/registry/*.yaml` are mapped under a synthetic, read-only category named `tool_catalog`, making them discoverable via `skills_list` and viewable via `skill_view` alongside native markdown skills.
- **Safety Boundaries**: To prevent security risks or accidental corruption of core definitions, skills under the `tool_catalog` category (stored in `tools/registry/`) are strictly read-only and protected from modification or deletion via `skill_manage`.

## Consequences

### Positive:
- **Token and Cost Efficiency**: Drastically reduces input token consumption by loading detailed files on demand rather than eagerly.
- **Agent Empowerment**: Gives agents a reliable discovery API to search and inspect available workspace resources.
- **Dynamic Adaptability**: Enables autonomous agents to save successful patterns as reusable skills, allowing the agent to "evolve" its own capability library over time.
- **Unified Surface**: Merges developer guidelines and JSON/YAML tool registries into a single conceptual model.

### Negative:
- **Two-Step Latency**: If the agent is unaware of a skill's name, it must call `skills_list` first before it can retrieve the skill text via `skill_view`.
- **Workspace State Management**: Custom skills created via `skill_manage` are stored locally on disk under the workspace directory, requiring explicit backup/version control policies to persist across environment resets.

## Alternatives Considered

- **Injecting all guidelines at session boot**: Rejected because it causes massive input token bloat, high costs, and context dilution.
- **Standard RAG semantic search for skills**: Rejected because semantic search does not guarantee the agent finds a complete catalog, whereas a deterministic `skills_list` index ensures the agent has an exhaustive, structured view of available skills.
- **Separating tools from skills**: Rejected because unified discovery under one system (`skills_list` exposing both tool catalogs and markdown guides) provides a superior, consolidated capability discovery interface for the LLM.

## Revisit When
- The number of custom skills in `skills/` exceeds 100, which may require paginating the Level 0 `skills_list` output.
- LLM pricing or context-handling improves to the point where eager injection of full guidelines has negligible cost and latency.
