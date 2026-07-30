# ADR-025: Data Residency Tags + Lawful Erasure Request Ledger

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-024 shipped egress privacy hashing and an informative GDPR/DPDP map,
but still deferred data-residency controls and lawful erasure vs WORM
policy. Operators need a region stamp on evidence egress and an
append-only erasure *request* ledger — without rewriting sealed cold
store or claiming a hardware WORM appliance.

## Decision

1. **`audit_residency`** — default off; stamps `residency_region` on
   export / SIEM / CLI when enabled (egress only)
2. **`audit_erasure` + `ErasureLedger`** — side SQLite
   (`data/erasure_requests.db`); records requests; classifies
   `blocked_sealed` when decision ids fall in sealed WORM ranges
3. Hot follow-up remains **ADR-019 retention** only — this ADR never
   calls `delete_through` itself and never mutates sealed JSONL
4. Publish residency/erasure rows into the GDPR/DPDP compliance map
5. Hardware WORM appliance remains deferred

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Rewrite / delete sealed WORM on erasure | Breaks immutability; legal design required |
| Schema UPDATE tombstones on hashed fields | Breaks ADR-017 chain |
| Auto-run retention from erasure | Couples legal workflow to ops; keep explicit |

## Consequences

**Positive:** Region visible on egress; erasure requests are auditable;
sealed overlap is explicit (`blocked_sealed`).

**Negative:** Does not fulfil erasure for already-sealed evidence;
hardware WORM / full residency transfer mechanisms still out of scope.

## Revisit when

~~Automated transfer pipeline~~ — **ADR-027.**
A funded deploy specifies hardware WORM, sealed-cold crypto-shred, or
IdP-backed data-subject portals.
