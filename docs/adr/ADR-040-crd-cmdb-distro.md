# ADR-040: CRD Packaging + Commercial CMDB + Distro Packages

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-039 shipped in-cluster FakeInformer reconcile, generic CMDB HTTP sync,
and systemd timer unit stubs. Remaining mesh packaging work was
operator-sdk/CRD documents, commercial CMDB connectors (ServiceNow /
Device42-style), and `.deb`/`.rpm` metadata — without hard deps or root
installs in CI.

## Decision

1. **`runtime/k8s_crd.py`** + **`deploy/k8s/crds/`** — render/validate
   `NatsBroker` CRD; apply CR instances via Fake or soft kubectl
2. **`runtime/cmdb_commercial.py`** — ServiceNow / Device42 Fake + soft
   HTTP sync into `FleetInventory`
3. **`runtime/distro_packages.py`** + **`deploy/packaging/`** — render
   deb control / rpm spec; write stubs when `allow_write`; install stage
   only with `allow_install` (never invokes dpkg/rpm as root by default)
4. Config: `supercluster.k8s_crd`, `supercluster.cmdb_commercial`,
   `actor_mesh.distro_packages` (default off)

Out of scope: real operator-sdk Go project, certified vendor SDKs,
publishing to apt/yum mirrors, production in-cluster CRD controllers.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Hard-require operator-sdk / pysnow | Ops weight; CI must stay soft |
| Always write under /etc or system package dirs | Dangerous default |
| Skip commercial CMDB entirely | Contract-only remaining item |

## Consequences

**Positive:** CRD YAML and distro metadata are testable; commercial CMDB
can seed inventory without live credentials.

**Negative:** Not a live operator or published package; live HTTP /
kubectl / install remain opt-in.

## Revisit when

~~Live operator-sdk / vendor CMDB SDKs / apt-yum publish~~ — **ADR-042.**
A contract funds a real Go/Helm operator project, certified vendor
partnerships, or remote mirror publish automation.
