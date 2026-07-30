# ISO 27001 — Audit Logging Control Map (KerrOS)

**Status:** Informative foundation (ADR-022)  
**Not:** a Statement of Applicability, risk register, or certification pack.

Maps selected ISO/IEC 27001:2022 themes (A.8 asset / information handling
and A.12 operations security — logging) to KerrOS artifacts already in tree.

| Theme (abbrev.) | Intent | KerrOS artifact |
|-----------------|--------|-----------------|
| A.12.4 Logging | Privileged / security events recorded | `kernel/decision_log.py` append-only log (KOS-008) |
| A.12.4 Log integrity | Detect tampering | Hash chain `prev_hash` / `entry_hash` + `verify_chain()` ([ADR-017](../adr/ADR-017-decision-log-tamper-evidence-export.md)) |
| A.12.4 Log protection | Protect evidence at rest | Software-WORM sealed JSONL ([ADR-019](../adr/ADR-019-decision-log-worm-retention.md)); optional Object Lock / local compliance mirror ([ADR-022](../adr/ADR-022-decision-log-object-lock-iso-map.md)) |
| A.12.4 Admin access | Restrict who can export / purge | Token RBAC reader/operator/admin ([ADR-021](../adr/ADR-021-decision-log-rbac-siem.md)) |
| A.12.4 Monitoring | Forward events to ops tooling | Optional SIEM webhook/syslog ([ADR-021](../adr/ADR-021-decision-log-rbac-siem.md)) |
| A.8 Evidence handling | Controlled retention of records | `audit_retention` archive → seal then prefix-delete ([ADR-019](../adr/ADR-019-decision-log-worm-retention.md)) |
| A.8 Cold storage | Off-host durable copy | `audit_object_lock` S3 Object Lock or `local_mirror` ([ADR-022](../adr/ADR-022-decision-log-object-lock-iso-map.md)) |

## Explicitly not covered here

- Full A.5–A.18 control catalog / SoA  
- ~~Local data-residency / privacy-act ADRs~~ — GDPR/DPDP map [ADR-024](../adr/ADR-024-jurisdiction-privacy-foundation.md); residency stamp + erasure ledger [ADR-025](../adr/ADR-025-residency-erasure-ledger.md); sealed-cold erasure / transfers still deferred  
- Hardware WORM appliances  
- IdP (OIDC/SAML) for evidence access  

Revisit those when a funded regulated deployment specifies them.
