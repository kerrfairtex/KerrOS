# ADR-022: Decision Log Object Lock Mirror + ISO 27001 Audit Map (LGU foundation)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-019 ships software-WORM sealed JSONL segments (`chmod 0444`). KOS-013
still deferred hardware WORM / Object Lock and an ISO compliance map.
Operators need an optional cold mirror into S3-compatible Object Lock (or a
local compliance copy) plus a short control→artifact map — without a
certification pack or hard `boto3` dependency.

## Decision

1. **`audit_object_lock`** — default off; backends `local_mirror` |
   `s3_object_lock` (soft-import boto3)
2. Hook after successful `WormStore.seal_from_log` (best-effort;
   `strict: true` fails the seal if mirror fails)
3. Publish [`docs/compliance/iso27001-audit-logging-map.md`](../compliance/iso27001-audit-logging-map.md)
   — ISO 27001 A.8 / A.12 themes → KerrOS audit artifacts (not a SoA)
4. Credentials via standard AWS env vars; no secrets in `config.json`

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Hard-require boto3 | Breaks Termux / slim CI |
| Full ISO certification pack | Out of scope for KerrOS foundation |
| In-process mTLS / NATS | Unrelated; already deferred elsewhere |

## Consequences

**Positive:** Sealed evidence can land in Object Lock buckets or a local
compliance mirror; auditors get a one-page control map.

**Negative:** Bucket Object Lock must be enabled by the operator; local
mirror is still OS-mutable by root; map is illustrative, not certification.

## Revisit when

A funded LGU contract supplies a WORM appliance, IdP-backed evidence access,
or a jurisdiction-specific privacy-act ADR.
