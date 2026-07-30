# ADR-042: Live Operator-SDK Controllers + Vendor CMDB SDKs + apt/yum Publish

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-040 shipped CRD YAML stubs, commercial CMDB HTTP facades, and
`.deb`/`.rpm` metadata. Remaining mesh packaging residuals were *live*
operator-sdk / controller-runtime loops, deep vendor CMDB SDKs
(pysnow / Device42), and apt/yum repository publish — without hard
deps or remote mirror pushes in CI.

## Decision

1. **`runtime/k8s_operator_sdk.py`** + **`deploy/k8s/operator/`** —
   Fake leader election + watch queue + reconcile; soft kubectl;
   optional project skeleton write; soft `operator-sdk init` probe
2. **`runtime/cmdb_vendor_sdk.py`** — Soft `pysnow` ServiceNow + Device42
   REST SDK facades; Fake when not `allow_live`
3. **`runtime/distro_publish.py`** — Fake apt/yum repo staging; soft
   `reprepro` / `createrepo(_c)`; remote mirror gated and never uploaded
   by default
4. Config: `supercluster.operator_sdk`, `supercluster.cmdb_vendor_sdk`,
   `actor_mesh.distro_publish` (default off)

Out of scope: shipping a Go operator-sdk binary, certified vendor
partnerships, pushing to public apt/yum mirrors.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Require operator-sdk / pysnow / reprepro in CI | Breaks default checkout |
| Auto-push to remote mirrors | Dangerous default |
| Skip — declare arc complete | Explicit residual from ADR-040 |

## Consequences

**Positive:** Controller reconcile, vendor SDK sync, and repo publish
are CI-testable with Fake backends.

**Negative:** Not a production Go operator or published mirror; live
tools remain opt-in.

## Revisit when

~~Go operator binaries / certified vendor partnerships / remote mirrors~~ — **ADR-043.**
A contract funds shipping a Go/Helm operator image, a vendor-issued
partnership certificate, or automated public apt/yum mirror publish.
