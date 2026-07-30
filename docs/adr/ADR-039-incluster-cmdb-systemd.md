# ADR-039: In-Cluster Operators + CMDB Sync + systemd Timers

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-038 shipped CMDB-lite inventory, a kubectl/Fake operator facade, and
a tickable ACME renewal timer. Remaining contract-only mesh work was
*in-cluster* reconcile loops, CMDB API sync, and distro systemd timer
packaging — without requiring a live API server or writing to `/etc`.

## Decision

1. **`runtime/k8s_incluster_operator.py`** — FakeInformer + reconcile
   loop; soft in-cluster SA detection; optional `require_in_cluster`
2. **`runtime/cmdb_client.py`** — Fake/HTTP CMDB sync into
   `FleetInventory`
3. **`runtime/systemd_timers.py`** + **`deploy/systemd/`** — render
   `kerros-acme-renew.service`/`.timer`; write under units_dir; install
   only with explicit `install_root` + `allow_install`
4. Config: `supercluster.k8s_incluster`, `supercluster.cmdb`,
   `actor_mesh.systemd_timers` (default off)

Out of scope: controller-runtime / CRDs in-cluster, commercial CMDB
products, packing distro packages (.deb/.rpm), auditor-signed SoA / SAML.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Full operator-sdk project | Ops weight; Fake informer enough |
| Always install to /etc/systemd | Dangerous default; gated install_root |
| Hard CMDB dependency | Soft HTTP + Fake |

## Consequences

**Positive:** In-cluster reconcile is testable; CMDB can seed inventory;
systemd units are renderable without root.

**Negative:** Not a production controller; live CMDB/kubectl/systemctl
remain opt-in.

## Revisit when

A contract funds CRD/operator-sdk packaging, commercial CMDB connectors,
or distro packages with packaged timer units.
