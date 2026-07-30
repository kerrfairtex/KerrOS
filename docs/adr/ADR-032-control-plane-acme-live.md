# ADR-032: Supercluster Control-Plane + ACME newAccount/Cloud DNS

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-031 shipped topology ops (plan/probe/apply ledger) and local ACME
account / in-memory DNS-01. Remaining deferred work on the mesh track was
a *live* Supercluster control-plane (config publish / monitor / reload
signal) and ACME `newAccount` + cloud DNS bridges — without hard AWS/GCP
SDKs or embedding `nats-server`.

## Decision

1. **`runtime/nats_supercluster_control.py`** — control-plane facade:
   publish rendered NATS snippets via memory/file backend, soft monitor
   URL probes, soft `nats-server --signal reload` probe
2. **`runtime/acme_new_account.py`** — `newAccount` client with fake
   transport (CI) + soft HTTP transport (opt-in); persists kid into the
   ADR-031 account registry
3. **`runtime/acme_cloud_dns.py`** — fake cloud + webhook DNS providers
   for DNS-01; no cloud SDKs (operator webhook bridge)
4. Config: `actor_mesh.supercluster.control_plane`,
   `actor_mesh.acme.new_account`, `actor_mesh.acme.dns01.cloud`
   (all default off)

Out of scope: spawning NATS brokers, full JOSE/JWS ACME client against
Let's Encrypt, AWS Route53 / Cloudflare SDKs, hardware WORM / IdP portals,
sealed-cold crypto-shred.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Embed nats-server process manager | Ops weight; Termux unfit |
| josepy / acme library newAccount | Hard deps; certbot remains ops path |
| boto3 / cloudflare SDK | Credential blast radius; webhook bridge enough |

## Consequences

**Positive:** Operators can publish intended Supercluster configs, probe
monitors, exercise newAccount via fake transport, and bridge DNS-01 to an
owned webhook.

**Negative:** File write / live POST / signal reload stay opt-in; real LE
issuance still needs certbot/acme with proper JWS.

## Revisit when

~~Broker lifecycle / ACME JOSE + cloud DNS SDKs~~ — **ADR-033.**
~~Hardware WORM / crypto-shred / IdP portals~~ — **ADR-034.**
A funded deploy needs multi-broker fleets, production ACME issuance, or certified SoA.
