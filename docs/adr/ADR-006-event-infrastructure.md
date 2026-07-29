# ADR-006: Event Infrastructure and Local LLM Adapters

**Status:** Accepted  
**Date:** 2026-07-23

## Context

Phase 2 delivered kerrd, service management, and health monitoring. README P3
requires event bus, scheduler, and workflow execution. The engineering backlog
Phase 3 trigger adds self-hosted models (Ollama/vLLM) behind the existing
`LLMPort` without kernel contract changes.

## Decision

Introduce Phase 3 runtime infrastructure:

1. **EventBus** — typed pub/sub with bounded history and wildcard listeners
2. **Scheduler** — in-process one-shot and interval jobs, publishing to EventBus
3. **WorkflowEngine** — DAG execution with step dependencies and audit events
4. **CompositeLLMAdapter** — Ollama and vLLM adapters with cloud fallback via
   existing `MultiAPIAdapter`

Kernel boot registers `event_bus`, `scheduler`, and `workflow_engine`. The
scheduler starts automatically on boot and stops on kernel shutdown.

Provider selection:

- `KERROS_LLM_PROVIDER` env (`cloud`, `ollama`, `vllm`, `local`)
- `KERROS_LOCAL_LLM=1` enables local-first fallback chain
- `provider_hint` kwarg on `LLMPort.complete()`

## Consequences

**Positive:**
- Workflows and scheduled jobs can react to kernel events without tight coupling
- Local GPU inference available without changing agent or kernel call sites
- CLI exposes `/events`, `/schedule`, `/workflows`, `/llm` for observability

**Negative:**
- In-process scheduler does not survive process restart
- Workflow **definitions** still require re-registration after restart (callables are not persisted); run **state** now checkpoints to SQLite (`runtime/workflow_store.py`)
- Local adapters require reachable OpenAI-compatible endpoints

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Reuse CompletionEventBus only | Completion-specific; not kernel-integrated |
| Celery/APScheduler | Heavy dependency for single-node Phase 3 |
| Modify kernel LLMPort contract | Backlog explicitly requires adapter-only change |
| Embed Ollama in multi_api.py | Violates port/adapter boundary |
