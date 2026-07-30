# ADR-018: Actor Mesh Orchestrator Foundation (Named Routing + Req/Reply + WAN Dial)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-012 shipped actor-mesh topic fanout; ADR-014 added shared-secret
envelopes. PHASE2/PHASE3 still deferred “full actor orchestrator /
authenticated WAN.” Operators need named actors, request/reply, and late
peer dial without adopting NATS/mTLS or a supervision runtime.

## Decision

Extend `runtime/actor_mesh.py` (no parallel orchestrator module):

1. `ActorMessage.actor` + `target_node` (empty target = fanout as before)
2. `ActorMesh.register` / `set_route` / `request` / `reply`
3. `SocketActorBackend.dial` + `ActorMesh.add_peer` for post-attach WAN join
4. Config `actor_mesh.routes` / `KERROS_ACTOR_MESH_ROUTES`
5. Optional `auth_required_non_loopback` — refuse non-loopback listen without token
6. Reuse ADR-014 `MeshAuth` envelopes; TLS stays external (proxy)

Out of scope: remote supervision trees, capability-based routing,
exactly-once delivery, in-repo mTLS.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| New `actor_orchestrator.py` | Duplicates mesh; harder to keep auth/backends in sync |
| HTTP actor ingest like event mesh | Different semantics; TCP mesh already exists |
| Require TLS in-process | Breaks Termux/CI; ADR-014 already chose token + proxy TLS |

## Consequences

**Positive:** Two nodes can RPC named actors; droplet can `add_peer` after
boot; non-loopback can be gated on a token.

**Negative:** Routing table is static/in-memory (no gossip); bus still
fans frames to all connections (receivers filter on `target_node`).

## Revisit when

~~Local actor heartbeats / liveness~~ — **ADR-020.**
~~mTLS / NATS / remote process restart hook~~ — **ADR-023.**
~~JetStream soft / OTP local tree / CA reload~~ — **ADR-028.**
~~JetStream cluster failover + ACME watch~~ — **ADR-029.**
~~Supercluster topology / ACME HTTP-01~~ — **ADR-030.**
~~Supercluster topology ops / ACME account+DNS-01~~ — **ADR-031.**
~~Supercluster control-plane / ACME newAccount+cloud DNS~~ — **ADR-032.**
~~Broker lifecycle / ACME JOSE + cloud DNS SDKs~~ — **ADR-033.**
~~Hardware WORM / crypto-shred / IdP portals~~ — **ADR-034.**
~~Multi-broker fleets / ACME issuance~~ — **ADR-035.**
~~SoA draft / OIDC RP~~ — **ADR-036.**
~~Remote fleet orchestration / packaged production ACME~~ — **ADR-037.**
~~Inventory / K8s operator / ACME renewal timers~~ — **ADR-038.**
~~In-cluster operators / CMDB / systemd timers~~ — **ADR-039.**
~~CRD packaging / commercial CMDB / distro packages~~ — **ADR-040.**
~~Auditor-signed SoA / SAML SP~~ — **ADR-041.**
~~Live operator-sdk / vendor CMDB SDKs / apt-yum publish~~ — **ADR-042.**
~~Go operator binaries / certified vendor partnerships / remote mirrors~~ — **ADR-043.**
~~Auditor evidence packs / production SAML federation~~ — **ADR-044.**
Remaining: shipped Go/Helm images / vendor-issued certificates / public apt-yum mirrors / auditor-issued certificates / full XMLDSig when funded.
