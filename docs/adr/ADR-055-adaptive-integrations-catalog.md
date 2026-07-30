# ADR-055: Adaptive Integrations Catalog (coding & execution)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Operators hold many local API keys (coding agents, research APIs, DevOps,
multi-agent frameworks) in gitignored `.env` files. KerrOS already had a
partial `api_config.yaml` registry, but gaps remained (CrewAI, AutoGen,
academic writing APIs, coding tiers) and there was no soft status surface
beyond session `/apistatus` health.

## Decision

1. Expand **`api_config.yaml`** with missing catalog entries and
   **coding / research** routing tiers alongside Sol / Terra / Luna.
2. Expand **`.env.example`** with matching env slots (never commit secrets).
3. Add **`adapters/integrations/registry.py`** — soft readiness report +
   tier resolver; never prints secret values.
4. Enhance **`api_status.py`** and CLI **`/integrations`** / `/apistatus`.
5. Register a capability manifest
   **`config/capabilities/adaptive_integrations.yaml`**.
6. Prefer model IDs for coding-heavy providers:
   Claude Opus 4.7, GPT-5.2, DeepSeek-Reasoner (operator may override).

Out of scope: bundling CrewAI/AutoGen/Aider SDKs in core deps, live calls
in CI, replacing MemoryPort with pgvector, production seals.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Full SDK adapters per vendor | Huge surface; most keys never used in CI |
| Require all keys in cloud secrets | Operator keeps keys local + gitignored |
| Make pgvector primary memory | Conflicts with ADR-015/051 FTS-primary |

## Consequences

**Positive:** One catalog + adaptive coding tier for local keys.

**Negative:** Catalog ≠ live SDK; many entries stay `needs_setup` until
keys/CLIs exist on that host.

## Revisit when

A funded deploy needs first-class CrewAI/AutoGen runners or pgvector as
a MemoryPort backend.
