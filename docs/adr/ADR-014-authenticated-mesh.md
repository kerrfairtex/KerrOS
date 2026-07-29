# ADR-014: Authenticated Mesh (Shared Secret)

**Status:** Accepted  
**Date:** 2026-07-29

## Context

ADR-011 (Docker HTTP mesh) and ADR-012 (actor mesh) ship without wire auth and
document loopback / private-network binding. Operators asked for an
**authenticated mesh** before any non-lab exposure. Full mTLS / NATS is still
heavy for KerrOS’s Termux + droplet posture.

## Decision

Add a **shared-secret** layer (`runtime/mesh_auth.py`):

1. **`MeshAuth`** — `token` + optional `auth_required` (refuse start if empty)
2. **HTTP event mesh** — when token set, `POST /mesh/ingest` and
   `/mesh/publish` require `Authorization: Bearer …` or
   `X-Kerros-Mesh-Token`; `GET /health` stays open for probes
3. **Outbound HTTP transport** — sends the same headers
4. **Actor mesh** — envelopes `{token, msg}` when token set; reject on mismatch
5. Env: `KERROS_EVENT_MESH_TOKEN` / `KERROS_ACTOR_MESH_TOKEN`; Compose kit
   defaults to a lab token (must be rotated)

Empty token keeps prior open behavior for local unit tests.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| mTLS only | Cert ops burden for foundation |
| JWT with expiry/issuer | Overkill vs shared lab/cluster secret |
| Always-on auth with no empty-token mode | Breaks existing ADR-011 tests/CI |

## Consequences

**Positive:** Unauthenticated POSTs get 401; Docker verify checks reject path;
actor mesh drops bad envelopes.

**Negative:** Shared secret is not TLS; replay/MITM on a hostile network still
possible — bind privately or terminate TLS at a proxy.

## Revisit when

Public edge exposure or multi-tenant mesh is required — add TLS (or NATS) in
front of the same transports.
