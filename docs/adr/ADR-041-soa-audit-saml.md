# ADR-041: Auditor-Signed SoA + SAML SP Foundation

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-036 shipped ISO SoA draft JSON and an OIDC relying-party foundation.
Remaining LGU compliance work was auditor-style detached signatures over
the SoA draft and SAML 2.0 SP plumbing — without claiming certification
or hard-requiring pysaml2.

## Decision

1. **`adapters/compliance/soa_audit.py`** — FakeSigner (HMAC) or soft
   openssl detached signature over SoA draft JSON; optional write of
   `soa_draft.sig.json`
2. **`adapters/auth/saml_sp.py`** — Fake IdP + AuthnRequest / ACS consume
   foundation; soft live decode only when `allow_live`
3. Config: `soa_audit`, `saml_sp` (default off)

Out of scope: certified auditor evidence packs, production SAML crypto
(XML signatures / encryption), enterprise IdP federation catalogs.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Claim ISO certification from draft SoA | Misleading; foundations only |
| Hard-require pysaml2 / python3-saml | Optional soft probe enough |
| Skip SAML because OIDC exists | Contract residual explicitly listed |

## Consequences

**Positive:** SoA signature envelopes and SAML ACS flows are CI-testable
without live auditors or IdPs.

**Negative:** Not a certification claim; live openssl / SAML bindings
remain opt-in.

## Revisit when

~~Auditor evidence packs / production SAML federation~~ — **ADR-044.**
An LGU contract funds auditor-issued evidence certificates or full
XMLDSig / encrypted-assertion production federation.
