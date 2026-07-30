# ADR-036: Certified SoA Draft + Full OIDC RP Foundation

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-034 shipped hardware WORM / crypto-shred / IdP portal facades.
Remaining LGU funded work was a certified Statement of Applicability
(SoA) pack and a full OIDC relying party — without claiming auditor
certification or hard-requiring Authlib.

## Decision

1. **`adapters/compliance/soa.py`** + **`docs/compliance/soa-foundation.md`**
   — structured SoA *draft* mapping ISO 27001:2022 themes → KerrOS
   artifacts (`planned|partial|implemented`); optional JSON write
2. **`adapters/auth/oidc_rp.py`** — authorization-code RP with PKCE,
   Fake IdP for CI, soft live token exchange when `allow_live`
3. Config: `compliance_soa`, `oidc_rp` (default off)

Out of scope: auditor-signed SoA / certification evidence packs, SAML,
mandatory Authlib dependency.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Claim certified SoA in-repo | False assurance; draft only |
| Hard-require Authlib | Soft Fake + urllib enough for foundation |

## Consequences

**Positive:** Operators can generate an SoA draft and run OIDC code-flow
in CI against a Fake IdP.

**Negative:** Not a certification pack; live IdP exchange remains opt-in.

## Revisit when

~~Auditor-signed SoA / SAML SP foundation~~ — **ADR-041.**
An LGU contract funds auditor evidence packs or production SAML federation.
