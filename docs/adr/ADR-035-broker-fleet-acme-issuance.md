# ADR-035: Multi-Broker Fleets + Production ACME Issuance

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-033 shipped single-broker lifecycle and soft JOSE/order helpers.
Remaining funded mesh work was multi-broker *fleets* and a production-
shaped ACME issuance pipeline — without requiring live `nats-server` or
a full Let's Encrypt client in CI.

## Decision

1. **`runtime/nats_broker_fleet.py`** — named fleet of
   `NatsBrokerLifecycle` members; start/stop/restart/health aggregate
2. **`runtime/acme_issuance.py`** — fake order→challenge→finalize→cert
   PEM stub; live mode soft-skips to external ACME clients
3. Config: `actor_mesh.supercluster.broker_fleet`,
   `actor_mesh.acme.issuance` (default off)

Out of scope: orchestrating remote hosts, real LE production issuance,
certified compliance packs (ADR-036).

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Always spawn N brokers in CI | Breaks slim environments |
| Embed certbot/acme.sh issuance | Ops tool remains external; fake path enough |

## Consequences

**Positive:** Operators can model multi-broker fleets and exercise an
issuance pipeline in CI.

**Negative:** Live LE still needs an external ACME client; fleet spawn
stays opt-in.

## Revisit when

~~Remote fleet orchestration / packaged production ACME~~ — **ADR-037.**
A contract funds inventory-driven orchestration, Kubernetes operators, or
fully automated production LE renewal timers.
