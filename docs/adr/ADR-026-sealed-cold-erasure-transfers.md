# ADR-026: Sealed-Cold Erasure Review + Cross-Border Transfer Ledger

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-025 records erasure requests and marks sealed overlaps
`blocked_sealed`, but leaves sealed-cold review and cross-border transfer
mechanisms unresolved. Operators need an auditable review workflow for
immutable cold evidence and a transfer-*intent* ledger — without a
hardware WORM appliance or rewriting sealed JSONL.

## Decision

1. **`review_sealed_erasure`** — append-only review outcomes for
   `blocked_sealed` requests: `legal_hold_retain` |
   `acknowledged_immutable` | `schedule_post_retention` (never mutates WORM)
2. **`audit_transfers` + `TransferLedger`** — side SQLite recording
   from/to region + mechanism (`scc` | `adequacy` | `consent` |
   `derogation` | `internal`); default off; does not move bytes
3. Publish [`docs/compliance/cross-border-transfer-map.md`](../compliance/cross-border-transfer-map.md)
4. Hardware WORM appliance remains deferred

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Delete / rewrite sealed WORM on review | Breaks ADR-017/019 immutability |
| Auto-transfer over HTTP | Out of scope; operators own channels |
| Hardware WORM now | Still needs funded appliance |

## Consequences

**Positive:** Sealed-cold decisions and transfer intents are auditable;
WORM verify remains green after review.

**Negative:** Does not erase sealed cold bytes; does not execute transfers;
hardware WORM / IdP portals still out of scope.

## Revisit when

~~Automated transfer pipeline (copy / HTTP PUT)~~ — **ADR-027.**
A funded deploy supplies hardware WORM, sealed-cold crypto-shred, or
IdP-backed data-subject portals.
