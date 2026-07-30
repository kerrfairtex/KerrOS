# GDPR / DPDP — Audit Logging Privacy Map (KerrOS)

**Status:** Informative foundation (ADR-024)  
**Not:** a DPIA, Record of Processing, DPDP consent register, or certification pack.

Maps selected privacy themes from GDPR (EU) and India’s DPDP Act (high-level)
to KerrOS audit artifacts. Jurisdiction-specific legal advice is out of scope.

| Theme (abbrev.) | Intent | KerrOS artifact |
|-----------------|--------|-----------------|
| Purpose limitation | Record why processing happened | `decision_type` / `outcome` / `reason` on `decision_log` |
| Integrity | Detect tampering of records | Hash chain ([ADR-017](../adr/ADR-017-decision-log-tamper-evidence-export.md)) |
| Security of processing | Protect logs in transit / at rest | RBAC + SIEM ([ADR-021](../adr/ADR-021-decision-log-rbac-siem.md)); software-WORM + Object Lock soft ([ADR-019](../adr/ADR-019-decision-log-worm-retention.md) / [ADR-022](../adr/ADR-022-decision-log-object-lock-iso-map.md)) |
| Data minimisation (egress) | Limit PII leaving the host | Optional egress hash/redact ([ADR-024](../adr/ADR-024-jurisdiction-privacy-foundation.md)); writer-side subject hash (KOS-010 in router) |
| Storage limitation | Bounded retention | `audit_retention` ([ADR-019](../adr/ADR-019-decision-log-worm-retention.md)) |
| Access control | Who may export evidence | Token RBAC ([ADR-021](../adr/ADR-021-decision-log-rbac-siem.md)) |

## Explicitly not covered here

- Lawful erasure vs WORM conflict resolution  
- Cross-border data-residency / transfer mechanisms  
- Hardware WORM appliances / full SoA  
- IdP-backed data-subject access portals  

Revisit those when a funded regulated deployment specifies them.
