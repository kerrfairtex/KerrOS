# ADR-045: Auditor-Issued Certificates + Full XMLDSig

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-044 shipped evidence pack assembly and multi-IdP SAML federation with
Fake HMAC XML stubs. Remaining LGU residuals were *auditor-issued
certificates* bound to pack digests and *full XMLDSig / XML encryption*
envelopes — without claiming ISO conformity or hard-requiring xmlsec.

## Decision

1. **`adapters/compliance/auditor_cert.py`** — Fake/soft openssl auditor
   CA; issue/verify cert envelopes over evidence `pack_sha256`;
   `certification` / `iso_certified` stay False (even with `allow_claim`)
2. **`adapters/auth/xmldsig.py`** — XMLDSig-shaped SignedInfo /
   SignatureValue / DigestValue; Fake c14n + HMAC; soft xmlsec/openssl;
   EncryptedData stubs when `allow_encryption`
3. Config: `auditor_cert`, `saml_xmldsig` (default off)

Out of scope: ISO/IEC 27001 certificates of conformity from accredited
bodies, production xmlsec templates with HSM keys, federation-hub
metadata crawlers.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Auto-set iso_certified=True on issue | Misleading / compliance risk |
| Hard-require xmlsec in CI | Soft probe enough |
| Skip — declare LGU arc complete | Explicit residual from ADR-044 |

## Consequences

**Positive:** Auditor cert envelopes and XMLDSig-shaped crypto are
CI-testable.

**Negative:** Not an accredited ISO cert or production XMLDSig; live
tools remain opt-in.

## Revisit when

An LGU contract funds accredited auditor certificates or production
xmlsec/HSM-backed XMLDSig and XML encryption.
