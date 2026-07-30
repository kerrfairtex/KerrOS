# KerrOS governance decision — KOS-013

**Date:** 2026-07-23  
**Status:** Accepted  
**Decision owner:** KerrOS engineering (default path until explicit LGU deployment)

## Question

Should KerrOS scope and audit features target:

1. **General-purpose** use for JOTHAM clients and private-sector workflows, or  
2. **LGU/government audit-grade** deployment with stricter immutability and compliance controls?

## Decision

**Adopt general-purpose scope as the default product posture**, with audit capabilities provided through the existing `decision_log` (KOS-008) and scope_gate fail-closed model (ADR-003).

LGU-grade extensions (immutable external audit export, WORM storage, role-based evidence retention) are **deferred to Phase 2** and will only be implemented when a concrete government or regulated deployment is funded and specified.

## Rationale

1. **Current users are JOTHAM clients** — verification, OSINT, and coding workflows need flexibility, not mandatory government audit packaging.
2. **P1 infrastructure is sufficient for accountability** — `decision_log` records scope, deploy, verification, and watchdog events without blocking general use.
3. **Premature LGU hardening adds cost** — WORM storage, certified retention, and LGU-specific RBAC are large Phase 2 items with no current deployment trigger.
4. **Fail-closed security is already in place** — scope_gate and deploy arm/disarm satisfy the safety bar for offensive/deploy tools without LGU-specific bureaucracy.

## Consequences

**Now (Phase 1):**
- Continue using SQLite WAL `decision_log` as the audit trail
- Hash PII in verification logs (KOS-010)
- Disarm deploy scope on watchdog restart (fail-closed)

**Phase 2 (trigger: LGU or regulated client contract):**
- ~~Add `MemoryPort` / `ToolPort` audit-immutability extensions~~ — foundation in ADR-017 (`tool_port` / `memory_port` decision_log hooks)
- ~~External audit export (signed JSONL or SIEM feed)~~ — JSONL + optional HMAC (`scripts/export_decision_log.py`); SIEM push in ADR-021
- ~~Retention policy engine~~ — foundation in ADR-019 (`audit_retention` + software-WORM); RBAC in ADR-021
- ~~ADR for LGU compliance mapping (ISO 27001)~~ — informative map in ADR-022; GDPR/DPDP egress map in ADR-024; residency stamp + erasure ledger in ADR-025; sealed-cold erasure / transfer mechanisms still deferred

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| LGU-first from day one | Blocks velocity; no funded LGU deployment yet |
| No audit at all | Contradicts ADR-003 and client trust requirements |
| Third-party SIEM only | Adds dependency before core log exists |

## Follow-up (Phase 2 only)

- ~~File issues for audit export adapter when LGU trigger fires~~ — landed: [`ADR-017`](../adr/ADR-017-decision-log-tamper-evidence-export.md)
- ~~Review `decision_log` schema for tamper-evidence (hash chain)~~ — `prev_hash` / `entry_hash` + `verify_chain()`
- ~~Document data residency requirements per jurisdiction~~ — region stamp foundation in [ADR-025](../adr/ADR-025-residency-erasure-ledger.md); transfer mechanisms still deferred
- ~~WORM storage, retention engine~~ — software-WORM segments + retention in [ADR-019](../adr/ADR-019-decision-log-worm-retention.md)
- ~~Role-based log access / SIEM~~ — foundation in [ADR-021](../adr/ADR-021-decision-log-rbac-siem.md)
- ~~Object Lock soft path + ISO audit map~~ — [ADR-022](../adr/ADR-022-decision-log-object-lock-iso-map.md)
- ~~Jurisdiction privacy egress + GDPR/DPDP map~~ — [ADR-024](../adr/ADR-024-jurisdiction-privacy-foundation.md)
- ~~Residency stamp + erasure request ledger~~ — [ADR-025](../adr/ADR-025-residency-erasure-ledger.md)
- Hardware WORM appliance / full SoA / sealed-cold erasure / cross-border transfers — still deferred until funded LGU deploy
