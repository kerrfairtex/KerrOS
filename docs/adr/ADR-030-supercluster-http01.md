# ADR-030: Supercluster Topology Registry + ACME HTTP-01 Solver

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-029 shipped client-side JetStream multi-URL failover and an ACME
live-dir watcher. PHASE2 still deferred NATS Supercluster / leafnode
topology management and ACME HTTP-01 challenge solvers. Operators need
an in-process topology registry for planning/health and a stdlib
HTTP-01 responder — without embedding a NATS server or registering
Let's Encrypt accounts.

## Decision

1. **`runtime/nats_supercluster.py`** — `SuperclusterTopology` registry
   for clusters, gateway links, and leafnodes; `validate()` for
   unknown/role errors; does **not** start brokers
2. **`runtime/acme_http01.py`** — `AcmeHttp01Solver` serves
   `/.well-known/acme-challenge/<token>` from an in-memory store
   (stdlib `ThreadingHTTPServer`); put/clear challenge APIs
3. Config: `actor_mesh.supercluster` and `actor_mesh.acme.http01`
   (both default off)

Out of scope: Supercluster topology *ops* (broker lifecycle, gateway
dial), ACME account registration / DNS-01, production certbot timers,
hardware WORM / IdP portals.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Embed NATS server Supercluster in-repo | Ops weight; Termux unfit |
| Full ACME client (account + order) | Hard deps; certbot/acme.sh remain ops tools |
| Require live brokers for topology tests | Breaks slim CI |

## Consequences

**Positive:** Operators can declare and validate multi-cluster topology
in config; HTTP-01 challenges can be answered in-process when enabled.

**Negative:** Topology is registry-only (no broker control plane); HTTP-01
does not issue certs — only serves challenge tokens.

## Revisit when

~~Supercluster topology ops / ACME account + DNS-01~~ — **ADR-031.**
~~Supercluster control-plane / ACME newAccount + cloud DNS~~ — **ADR-032.**
A funded deploy needs broker process lifecycle, full ACME JOSE / order
issuance, native cloud DNS SDKs, IdP portals, or hardware WORM /
sealed-cold crypto-shred.
