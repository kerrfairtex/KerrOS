# ADR-044: Auditor Evidence Packs + Production SAML Federation

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-041 shipped detached SoA signatures and a single-IdP SAML SP
foundation. Remaining LGU compliance residuals were *auditor evidence
packs* (SoA + signature + residual risks + control index) and
*production SAML federation* (multi-IdP catalog, signed/encrypted
assertion stubs) — without claiming ISO certification or hard-requiring
pysaml2/xmlsec.

## Decision

1. **`adapters/compliance/soa_evidence.py`** — assemble evidence pack
   (draft, signature, evidence index, residual risks, manifest); optional
   zip; Fake/soft openssl pack signing; `certification` always False
2. **`adapters/auth/saml_federation.py`** — multi-IdP federation catalog;
   Fake HMAC XML-signature stub; soft xmlsec/pysaml2 probes; optional
   soft-encrypted assertion wrap
3. Config: `soa_evidence`, `saml_federation` (default off)

Out of scope: real ISO auditor-issued certificates, full XMLDSig /
XML encryption with production keys, IdP discovery catalogs from
federation hubs.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Auto-set certification=True on pack write | Misleading |
| Hard-require pysaml2 / xmlsec | Soft probe enough for CI |
| Skip — declare LGU arc complete | Explicit residual from ADR-041 |

## Consequences

**Positive:** Evidence packs and multi-IdP SSO flows are CI-testable.

**Negative:** Not a certified evidence pack or production XML crypto;
live tools remain opt-in.

## Revisit when

~~Auditor-issued certificates / full XMLDSig~~ — **ADR-045.**
An LGU contract funds accredited auditor certificates or production
xmlsec/HSM-backed XMLDSig and XML encryption.
