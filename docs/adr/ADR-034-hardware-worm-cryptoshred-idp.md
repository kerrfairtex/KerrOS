# ADR-034: Hardware WORM + Crypto-Shred + IdP Portals

**Status:** Accepted  
**Date:** 2026-07-30

## Context

LGU deferred work after ADR-022..027 still listed hardware WORM
appliances, sealed-cold crypto-shred (destroy readability without
rewriting sealed bytes), and IdP-backed data-subject portals. Operators
need CI-safe facades that compose with software-WORM and the erasure
ledger without claiming full SoA certification.

## Decision

1. **`adapters/audit/hardware_worm.py`** — fake + soft HTTP appliance
   mirror for sealed segments (refuse overwrite; never mutates local WORM)
2. **`adapters/audit/crypto_shred.py`** — DEK keystore + gated `shred()`
   that nulls keys while leaving sealed ciphertext untouched
3. **`adapters/auth/idp_portal.py`** — Fake OIDC IdP + data-subject
   portal sessions for access/erasure intents (optional erasure ledger hook);
   soft OIDC discovery probe
4. Config: `audit_hardware_worm`, `audit_crypto_shred`, `idp_portal`
   (all default off)

Out of scope: certified hardware appliance drivers, full OIDC RP / SAML,
destroying sealed JSONL files, mandatory cryptography package.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Rewrite/delete sealed WORM on shred | Violates ADR-019 immutability |
| Full Authlib OIDC RP | Dep weight; portal facade is enough |
| Require appliance SDK | Soft HTTP + fake covers foundation |

## Consequences

**Positive:** Crypto-shred can render subject data unreadable without
touching WORM; portals can file erasure intents; appliance mirror is
testable in CI.

**Negative:** Not a certified WORM appliance or production IdP; shred
requires explicit `allow_shred`.

## Revisit when

~~SoA draft / OIDC RP~~ — **ADR-036.**
~~Auditor-signed SoA / SAML SP~~ — **ADR-041.**
~~Auditor evidence packs / production SAML federation~~ — **ADR-044.**
~~Auditor-issued certificates / full XMLDSig~~ — **ADR-045.**
An LGU contract funds accredited ISO certificates or HSM-backed XMLDSig.
