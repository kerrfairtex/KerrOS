# ADR-024: Jurisdiction Privacy Foundation (GDPR / DPDP audit map)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-017..022 shipped tamper-evident decision_log, software-WORM, RBAC/SIEM,
and an ISO audit map. KOS-013 still deferred jurisdiction privacy-act work.
Operators need an informative GDPR/DPDP → KerrOS map plus optional **egress**
PII hashing/redaction — without rewriting sealed evidence or claiming
certification.

## Decision

1. **`audit_privacy`** — default off; modes `hash` | `redact`; fields and
   channels (`export`, `siem`, `cli_read`) configurable
2. Transform **egress only** — never mutate SQLite / WORM sealed JSONL
   (would break ADR-017 hash chain)
3. Publish [`docs/compliance/gdpr-dpdp-audit-logging-map.md`](../compliance/gdpr-dpdp-audit-logging-map.md)
   — informative themes → artifacts (not a DPIA / SoA)
4. Salt via `KERROS_AUDIT_PRIVACY_SALT` (prefer env over config.json)

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Rewrite stored rows on “erasure” | Conflicts with WORM / hash chain; needs funded legal design |
| Always-on redaction | Breaks ops debugging; default must stay open for general-purpose |
| Hardware WORM now | Still needs funded appliance (out of scope) |

## Consequences

**Positive:** Exports/SIEM/CLI can hide subjects; auditors get a one-page
privacy theme map; chain verify remains on raw store.

**Negative:** Sealed WORM still holds plaintext unless writer-side hashing
(KOS-010) was used; lawful erasure vs immutability remains unresolved.

## Revisit when

~~Sealed-cold erasure review + cross-border transfer ledger~~ — **ADR-026.**
A funded jurisdiction deploy specifies DPIA/SoA, destroying sealed cold
bytes, automated transfer pipelines, or a hardware WORM appliance.
