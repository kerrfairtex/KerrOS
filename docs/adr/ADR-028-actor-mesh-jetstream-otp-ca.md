# ADR-028: Actor Mesh JetStream Soft Client + OTP Tree + CA Reload

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-023 shipped socket mTLS, soft NATS, and ServiceManager restart hooks.
PHASE2/PHASE3 still deferred JetStream HA, OTP supervision trees, and
production CA rotation. Operators need durable-pub soft API, a local
one-for-one supervision tree, and PEM mtime-based TLS reload — without
hard deps or a funded CA/JetStream cluster.

## Decision

1. **`runtime/nats_jetstream.py`** — soft JetStream client (default off);
   `InMemoryJetStreamClient` for CI; real path soft-imports nats-py
2. **`runtime/actor_supervision_tree.py`** — local OTP-style
   `SupervisionTree` (`one_for_one` / `one_for_all`); parent DEAD forgets
   child actors
3. **`ReloadingTlsHolder`** in `actor_mesh_tls.py` — rebuild SSL contexts
   when PEM mtimes change (`tls.reload`)
4. Wire onto `ActorMesh` as optional `jetstream` / `supervision_tree` /
   `tls_holder`

Out of scope: multi-server JetStream cluster ops, full OTP strategies
beyond local registry, ACME / automated CA issuance.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Require nats-py + live JetStream | Breaks Termux / slim CI |
| Full OTP process trees | Process spawn already optional via ADR-023 hook |
| ACME CA automation | Ops-specific; mtime reload is enough foundation |

## Consequences

**Positive:** Durable pub can be tested in-memory; parent death cascades
locally; cert rotation can reload without process restart.

**Negative:** Not HA JetStream; existing TLS connections keep old
contexts until re-dial; tree does not spawn processes.

## Revisit when

~~JetStream cluster failover + ACME live-dir watch~~ — **ADR-029.**
~~Supercluster topology / ACME HTTP-01~~ — **ADR-030.**
~~Supercluster topology ops / ACME account+DNS-01~~ — **ADR-031.**
~~Supercluster control-plane / ACME newAccount+cloud DNS~~ — **ADR-032.**
A funded deploy needs broker process lifecycle, full ACME JOSE+native cloud
DNS, IdP portals, or hardware WORM.
