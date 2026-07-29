# ADR-012: IPC Actor-Mesh Foundation (C-16)

**Status:** Accepted  
**Date:** 2026-07-29

## Context

ADR-005 shipped an in-process `ServiceBus` and explicitly deferred
“nng/socket mesh”. The engineering backlog’s C-16 is **IPC actor-mesh
(nng/socket)**. EventBus already has HTTP/Docker and durable transports
(ADR-008/009/011); service lifecycle traffic needs a separate,
optional cross-process seam that works on Termux (no hard native dep).

## Decision

Ship an **actor-mesh foundation**:

1. `ActorMessage` + `ActorMeshBackend` Protocol
2. **`SocketActorBackend`** — stdlib TCP length-prefixed JSON (always on)
3. **`NngActorBackend`** — pynng `Bus0` when installed; boot soft-falls back
   to socket if `backend=nng` but pynng is missing
4. `ActorMesh` — `publish(topic, payload)` fans out locally + remotely;
   inbound re-publishes on the local `ServiceBus`
5. Config `actor_mesh` / `KERROS_ACTOR_MESH=1` (disabled by default)
6. Register `service_bus` + optional `actor_mesh` in the kernel container

This is **not** a full AIOS actor orchestrator — no supervision of remote
actors, no capability routing, no exactly-once delivery.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Hard-require pynng | Breaks Termux / slim CI images |
| Reuse EventMesh HTTP for ServiceBus | Different bus + lifecycle semantics |
| Full nng actor runtime now | Premature vs ADR-004 narrow kernel |

## Consequences

**Positive:** Two processes can share service topics; nng path available when
`pynng` is installed; CI covered by socket backend.

**Negative:** Callers must use `ActorMesh.publish` (raw `ServiceBus.publish`
stays local). No auth on the wire — bind to loopback / private nets only.

## Revisit when

Multi-host authenticated service mesh is required — then put TLS or NATS
behind `ActorMeshBackend`, or graduate to a real actor runtime.
