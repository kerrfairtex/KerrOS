# ADR-008: Event Mesh Foundation (C-16 seam)

**Status:** Accepted  
**Date:** 2026-07-29

## Context

Phase 3 delivered an in-process `EventBus`. README / PHASE3 still deferred
“distributed event mesh across nodes (C-16)”. The engineering backlog’s C-16
originally meant IPC actor-mesh (nng/socket). Both need a **transport seam**
before any multi-node implementation.

## Decision

Ship an **event mesh foundation** without a durable broker:

1. `EventMeshTransport` Protocol (`send` / `close`)
2. `LocalEventMesh` — join N in-process `EventBus`es with loop-safe fanout
3. Stub transports: `NullEventMeshTransport`, `FileEventMeshTransport` (JSONL),
   `HttpEventMeshTransport` (POST peers; receive left to future webhook)
4. `Event.from_dict` / `EventBus.emit` for identity-preserving ingest
5. Config `event_mesh` (disabled by default); optional `KERROS_EVENT_MESH=1`

Kernel registers `event_mesh` only when enabled. Callers of `EventBus` need no
changes.

## Consequences

**Positive:** Later NATS/nng/Redis transports can implement the Protocol without
rewriting scheduler/workflows/OmniRoute telemetry.

**Negative / still deferred (partially addressed by ADR-009):** Docker mesh
(C-17), nng actor IPC, backpressure. Discovery + durable same-host broker
landed in ADR-009.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Celery / NATS / Redis Streams now | Heavy ops for single-node KerrOS |
| Merge ServiceBus into EventBus | ADR-005/006 keep lifecycle vs general events separate |
| nng actor mesh immediately | Premature; no funded multi-node trigger |
