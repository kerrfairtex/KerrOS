# ADR-027: Automated Transfer Pipeline Foundation

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-026 records cross-border transfer *intents* but does not move evidence.
PHASE2 still deferred automated transfer pipelines (and hardware WORM / IdP
portals). Operators need an opt-in copy pipeline that executes ledger rows
without rewriting sealed WORM sources.

## Decision

1. **`audit_transfers.execute_enabled`** — default off; backends
   `local_copy` | `http_put`
2. **`execute_transfer(request_id)`** — copies sealed segments and/or export
   JSONL into `dest_dir/{to_region}/transfer-{id}/`; writes
   `transfer_manifest.json`; marks ledger `executed` / `failed`
3. Source sealed files stay `chmod 0444` / untouched (`worm_untouched`)
4. Hardware WORM appliance, destroying sealed cold bytes, and IdP portals
   remain deferred

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Always-on auto-transfer on intent insert | Dangerous; require explicit execute |
| Move / delete source WORM | Breaks immutability |
| Hardware WORM / IdP now | Still funded-appliance / IdP work |

## Consequences

**Positive:** Intents can be fulfilled as copies to an outbox or HTTP PUT;
auditable via ledger status + manifest.

**Negative:** HTTP PUT is best-effort single-file; no brokered HA pipeline;
hardware WORM / IdP / crypto-shred still out of scope.

## Revisit when

~~Hardware WORM / crypto-shred / IdP portals~~ — **ADR-034.**
A funded deploy supplies certified SoA, full OIDC RP, brokered
transfer HA, or IdP-backed data-subject portals.
