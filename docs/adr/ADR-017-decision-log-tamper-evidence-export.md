# ADR-017: Decision Log Tamper-Evidence + Audit Export (LGU foundation)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

KOS-013 chose **general-purpose** scope and deferred LGU-grade audit
immutability to Phase 2 (`docs/decisions/scope-lgu-vs-general.md`). Phase 1
already ships an append-only SQLite `decision_log` (KOS-008) wired to
scope_gate and verify_*. What was missing for the Phase 2 governance
follow-up: tamper-evidence, external export, and thin MemoryPort/ToolPort
audit hooks — without WORM/SIEM/RBAC until a funded LGU contract.

## Decision

1. Extend `decisions` with `prev_hash` / `entry_hash` (SHA-256 chain)
2. `DecisionLog.verify_chain()` + `iter_from(since_id)` for integrity/export
3. JSONL export via `adapters/audit/decision_log_export.py` and
   `scripts/export_decision_log.py` (optional `KERROS_AUDIT_HMAC_SECRET`)
4. Best-effort audit on `RouterAdapter.run_tool` and `RagStoreAdapter.upsert`
5. Keep public API append-only (no UPDATE/DELETE); one-time migration
   backfill via `PRAGMA user_version = 2`

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Full WORM / SIEM now | No funded LGU deploy; ops cost |
| Signed Merkle tree service | Overbuilt vs SQLite tip hash |
| Skip port audit hooks | Decision doc explicitly lists MemoryPort/ToolPort |

## Consequences

**Positive:** Operators can export and verify evidence; tampering of stored
payloads fails `verify_chain`; backlog Phase 2 LGU item has a foundation.

**Negative:** OS-level SQLite file remains mutable without external WORM;
HMAC is optional shared-secret, not a PKI signature.

## Revisit when

~~Retention + software-WORM~~ — **ADR-019.**
~~RBAC + SIEM forwarder~~ — **ADR-021.**
~~Object Lock soft path + ISO audit map~~ — **ADR-022.**
Remaining: hardware WORM appliance / full SoA when an LGU contract funds them.
