# ADR-011: Docker Multi-Node Event Mesh (C-17)

**Status:** Accepted  
**Date:** 2026-07-29

## Context

ADR-008/009 delivered an in-process mesh and a same-host durable SQLite
broker. PHASE2/PHASE3 deferred **Docker server deployment (C-17)**. Operators
need a reproducible two-node kit that exercises cross-container EventBus
fanout without adopting NATS/nng yet.

## Decision

Ship a **Docker Compose HTTP mesh kit**:

1. `EventMeshHttpServer` — stdlib listener: `GET /health`, `POST /mesh/ingest`,
   `POST /mesh/publish`
2. Env wiring: `KERROS_EVENT_MESH_*` (transport, listen, http peers, node id)
3. `deploy/event_mesh/` — Dockerfile + two-service compose (`node-a`/`node-b`)
   on a private bridge network; host ports **loopback-only**
4. `scripts/mesh_node.py` headless entrypoint; `scripts/event_mesh_docker.sh`
   for `up` / `verify` / `down`

HTTP transport (already stubbed for send) is the cross-container path;
durable/file remain for shared-filesystem same-host use.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Shared SQLite volume across containers | Fragile locking / not multi-host |
| NATS/Redis now | Ops weight beyond C-17 foundation |
| nng actor mesh | Still deferred (C-16 full) |

## Consequences

**Positive:** Two containers can exchange events; CI can guard loopback
publishes; ADR-009 revisit trigger for Docker is satisfied at foundation level.

**Negative:** Ingest has no auth — must stay on private Docker network +
loopback host publish. Not a WAN mesh.

## Revisit when

A third physical host or authenticated edge exposure is required — then put a
reverse proxy + auth (or NATS) behind the same `EventMeshTransport` Protocol.
