# ADR-031: Supercluster Topology Ops + ACME Account/DNS-01

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-030 shipped an in-memory Supercluster topology registry and an HTTP-01
solver. Remaining deferred work was topology *ops* (plan/probe/apply) and
ACME account registration / DNS-01. Operators need a CI-safe control-plane
stub and DNS-01 plumbing without embedding NATS servers or a full ACME
client that talks to Let's Encrypt by default.

## Decision

1. **`runtime/nats_supercluster_ops.py`** — plan gateway/leaf actions,
   soft TCP URL probes (opt-in), in-memory apply ledger, NATS config
   snippet render; does **not** start or reconfigure brokers
2. **`runtime/acme_account.py`** — local account JSON registry + dry-run
   register; optional soft ACME directory GET probe
3. **`runtime/acme_dns01.py`** — RFC 8555 DNS-01 TXT digest + in-memory
   provider put/clear/verify
4. Config: `actor_mesh.supercluster.ops`, `actor_mesh.acme.account`,
   `actor_mesh.acme.dns01` (all default off)

Out of scope: live NATS Supercluster control plane, ACME `newAccount` /
order issuance against LE, cloud DNS provider APIs, hardware WORM / IdP.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Full ACME client (josepy / acme) | Hard deps; breaks slim CI |
| Cloud DNS plugins (Route53 etc.) | Credential blast radius; memory provider enough for foundation |
| Auto-write NATS config to disk | Ops risk; render snippets only |

## Consequences

**Positive:** Operators can plan/probe topology and exercise DNS-01
challenge plumbing in CI; local ACME account stubs are inspectable.

**Negative:** Apply does not change brokers; account register is local-only;
DNS-01 does not publish to real DNS.

## Revisit when

~~Live Supercluster control-plane / ACME newAccount + cloud DNS~~ — **ADR-032.**
~~Broker lifecycle / ACME JOSE + cloud DNS SDKs~~ — **ADR-033.**
~~Hardware WORM / crypto-shred / IdP portals~~ — **ADR-034.**
A funded deploy needs multi-broker fleets, production ACME issuance, or certified SoA.
