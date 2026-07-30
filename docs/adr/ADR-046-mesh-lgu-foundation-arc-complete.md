# ADR-046: Mesh / LGU Foundation Arc Complete

**Status:** Accepted  
**Date:** 2026-07-30

## Context

From ADR-012 through ADR-045 the KerrOS tree carried a continuous
foundation program for:

- **Actor mesh / supercluster / ACME / fleet / K8s / CMDB / packaging**
  (ADR-012…033, 035, 037…043)
- **LGU audit immutability / privacy / compliance / SAML**
  (ADR-017…027, 034, 036, 041, 044, 045)

Each ADR shipped default-off Fake/soft stubs so CI never needs live
brokers, kube, vendor SDKs, accredited auditors, or HSM keys. The last
explicit residuals after ADR-045 were production-grade deliverables:

- Shipped Go/Helm operator images
- Vendor-issued partnership certificates
- Public apt/yum mirror publish
- Accredited ISO/IEC 27001 certificates of conformity
- HSM-backed xmlsec XMLDSig / XML encryption

Those items require funded contracts, external accreditation, or
production crypto hardware. They are out of scope for the in-repo
foundation arc.

## Decision

1. **Declare the mesh / LGU foundation arc complete** as of ADR-045
   (this decision recorded in ADR-046).
2. **Keep remaining residuals contract-only** — do not open further
   soft-stub ADRs for them unless a funded deploy specifies scope.
3. **Document the freeze** in PHASE2 deferred lists, ADR-012/018
   revisit trails, and `docs/decisions/scope-lgu-vs-general.md`.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Continue soft stubs for Go images / ISO certs / HSM xmlsec | Diminishing returns; residuals need real contracts |
| Delete Fake foundations | Breaks CI and funded-deploy on-ramps |
| Claim ISO certification from Fake packs | Compliance risk / misleading |

## Consequences

**Positive:** Clear stop-line for autonomous foundation work; funded
deploys know which ADRs to harden.

**Negative:** Production Go images, accredited certs, and HSM XMLDSig
remain unimplemented until contracted.

## Revisit when

~~Explicit soft on-ramps for the five residuals~~ — **ADR-047**
(operator-requested post-freeze stubs; still not production seals).

A funded contract turns on public push, vendor seal, CAB accreditation,
or HSM custody for a named deploy.
