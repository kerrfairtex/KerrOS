# ADR-009: Event Mesh Transport — Discovery + Durable Broker

**Status:** Accepted  
**Date:** 2026-07-29

## Context

ADR-008 shipped the `EventMeshTransport` Protocol and `LocalEventMesh` with
null/file/HTTP stubs. PHASE3 still deferred “multi-node discovery / durable
event broker”. Operators need same-host multi-process fanout that survives
process restarts without standing up NATS/Redis/nng.

## Decision

Extend the mesh with a **transport layer** (not a network mesh):

1. **`DurableEventBroker`** — SQLite `mesh_messages` + per-node `mesh_acks`
   (at-least-once; shared DB path for multi-process)
2. **`DurableEventMeshTransport`** — implements `EventMeshTransport.send`
3. **`FilePeerRegistry`** + broker `mesh_peers` heartbeats for membership
4. **`LocalEventMesh.poll()` / `peers()` / `heartbeat()`** for ingest + discovery
5. Config: `transport: "durable"`, `broker_db`, `discovery` / `discovery_dir`

nng actor IPC and Docker multi-node (C-17) stay deferred.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| NATS / Redis Streams now | Ops weight for single-node KerrOS |
| Replace file JSONL with durable only | File stub remains useful for tests |
| nng actor mesh immediately | No funded multi-node trigger (C-16 full) |

## Consequences

**Positive:** Two KerrOS processes sharing `broker.db` can exchange EventBus
events with ack-based durability and visible peer membership.

**Negative:** Not WAN-safe; SQLite locking assumes co-located processes.
Backpressure and exactly-once semantics are out of scope.

## Revisit when

A second physical node or Docker mesh (C-17) is required, or message volume
makes SQLite WAL contention measurable — then evaluate NATS/nng behind the
same Protocol.
