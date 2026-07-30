# ADR-047: Production Soft On-Ramps (Post ADR-046 Freeze)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

[ADR-046](ADR-046-mesh-lgu-foundation-arc-complete.md) froze the mesh/LGU
foundation arc and left five residuals as contract-only. Operators
explicitly requested soft, default-off on-ramps for those residuals so
funded deploys have CI-safe stubs without claiming production seals.

## Decision

1. **`runtime/k8s_helm_images.py`** — Helm chart render + Fake/soft
   `helm package` / `docker push` (never public by default)
2. **`runtime/cmdb_vendor_issued.py`** — vendor-issued partnership cert
   envelopes (`vendor_sealed` always False)
3. **`runtime/distro_public_mirror.py`** — public apt/yum staging;
   push only with explicit `allow_public`
4. **`adapters/compliance/iso_certificate.py`** — ISO CoC envelopes;
   `iso_accredited` only if `allow_accredited` + live CAB confirm
5. **`adapters/auth/hsm_xmlsec.py`** — Fake HSM + soft PKCS#11/xmlsec
   probes over ADR-045 XMLDSig envelopes
6. Config slots under `actor_mesh` / top-level (default off)
7. **ADR-046 remains the freeze** — ADR-047 is an explicit post-freeze
   soft on-ramp, not a reopen of unbounded foundation churn

Out of scope: real public registry releases, vendor-sealed certificates,
accredited CAB issuance, production HSM custody.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Refuse because ADR-046 froze | Operator explicitly requested on-ramps |
| Auto-set accredited/sealed/public | Compliance risk |
| Require helm/docker/pkcs11 in CI | Soft Fake backends required |

## Consequences

**Positive:** Funded deploys can flip gates without inventing stubs.

**Negative:** Still not production seals; live tools remain opt-in.

## Revisit when

A funded contract turns on public push, vendor seal, CAB accreditation,
or HSM custody for a named deploy.
