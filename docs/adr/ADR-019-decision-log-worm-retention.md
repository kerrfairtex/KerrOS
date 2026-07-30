# ADR-019: Decision Log Software-WORM Segments + Retention Policy (LGU foundation)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-017 added hash-chained `decision_log` and JSONL export. KOS-013 still
deferred WORM storage and a retention policy engine until LGU needs appear.
Operators need a cold sealed archive path without a WORM appliance, SIEM, or
RBAC stack.

## Decision

1. **Software WORM** — sealed JSONL segments under `data/audit_worm/segments/`
   (`chmod 0444` + `.manifest.json`); API refuses rewrite of sealed paths
2. **Hot SQLite** remains the append-only working log; public API still has no
   UPDATE/DELETE except retention’s internal `delete_through(..., _retention=True)`
3. **Retention** — config `audit_retention` (default `enabled: false`);
   actions `archive` (seal then prefix-delete) or `purge` (delete only;
   requires `allow_purge` and no sealed segments)
4. **`verify_chain`** anchors at the first remaining row’s `prev_hash`
   (may be a sealed tip after archive)
5. Scripts: `seal_decision_log.py`, `apply_retention.py`; CLI
   `/decisions seal` / `/decisions retain`

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Hardware WORM / S3 Object Lock now | No funded LGU appliance; ops-specific |
| Auto-delete sealed segments | Legal hold / retention of cold evidence is operator-owned |
| RBAC on log read | Deferred with SIEM / ISO mapping |

## Consequences

**Positive:** Aged audit rows can leave the hot DB into sealed segments;
chain integrity remains verifiable across hot + cold.

**Negative:** OS admins can still `chmod`/`rm` sealed files; this is
application-layer WORM, not compliance hardware.

## Revisit when

~~RBAC + SIEM~~ — **ADR-021.**
An LGU contract funds Object Lock / WORM NAS, IdP-backed evidence access,
or a compliance-mapping ADR.
