# ADR-064: Skills Hub, Channel Gateway, Process Backends

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-061–063 closed subagents, profile memory, tool search, exec guards,
agent cron, soft MCP, session store, compression, bg processes, and
lifecycle hooks. Remaining high-value gaps from the agent-runtime plan:
installable skill hub with quarantine/provenance, a messaging ingress
surface, and pluggable process backends (local/fake/docker Soft).

## Decision

1. **`tools/skills_guard.py` + `tools/skills_hub.py` + `tools/skill_provenance.py`**
   — scan → allow/quarantine/deny; local install under `skills/`; lockfile at
   `data/skills_hub/lock.json`; URL install Soft behind `KERROS_SKILLS_HUB_LIVE`.
2. **`gateway/webhook.py`** — loopback HTTP webhook (`KERROS_GATEWAY=1`) with
   `/v1/message`, `/v1/inbox`, optional token; no third-party chat SDKs.
3. **`tools/process_backends.py`** — `local` | `fake` | `docker` Soft
   (`KERROS_BG_BACKEND`, `KERROS_BG_DOCKER=1` for live docker); remote Soft
   fleet facade in ADR-077.

## Consequences

**Positive:** Operators can ingress chat via any bridge that POSTs JSON;
skills installs are scanned; CI can use fake bg backend.

**Negative:** Full Telegram/Discord adapters and sandboxed remote terminals
remain out of scope until funded.

## Revisit when

Platform-specific adapters or Daytona/Modal-class sandboxes are required.
