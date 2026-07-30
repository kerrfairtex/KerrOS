# ADR-038: Fleet Inventory + K8s Operator + ACME Renewal Timers

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-037 shipped remote fleet agents and packaged production ACME.
Remaining contract-only mesh work was inventory-driven orchestration,
Kubernetes operator facades, and automated LE renewal timers — without
embedding a real CMDB, controller-runtime, or certbot in CI.

## Decision

1. **`runtime/fleet_inventory.py`** — CMDB-lite host registry with
   optional JSON persist; exports ADR-037 remote-fleet host specs
2. **`runtime/k8s_operator.py`** — Fake cluster + soft `kubectl apply`
   for `NatsBroker` manifests; reconcile desired set
3. **`runtime/acme_renewal_timer.py`** — interval renewal driver with
   manual `tick()` for tests; can call production issuer or soft
   `certbot renew`
4. Config: `supercluster.inventory`, `supercluster.k8s_operator`,
   `acme.renewal` (default off)

Out of scope: full CMDB, real Kubernetes operators / CRDs in-cluster,
systemd timers packaging, auditor-signed SoA / SAML.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Headlamp/Backstage inventory | External product; JSON registry enough |
| kubebuilder operator project | Ops weight; Fake + kubectl soft enough |
| Always-on background renew in CI | Use tick(); autostart opt-in |

## Consequences

**Positive:** Inventory can seed remote fleets; K8s manifests are
testable; renewal can be driven on a timer or by tick.

**Negative:** Not a production controller; live kubectl/certbot opt-in.

## Revisit when

~~In-cluster operators / CMDB / systemd timers~~ — **ADR-039.**
~~CRD packaging / commercial CMDB / distro packages~~ — **ADR-040.**
A contract funds live operator-sdk controllers, vendor CMDB SDKs, or
apt/yum publish pipelines.
