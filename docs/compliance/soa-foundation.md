# ISO 27001 — Statement of Applicability Foundation (KerrOS)

**Status:** Draft foundation (ADR-036)  
**Not:** a certified SoA, risk register, or auditor evidence pack.

Use `adapters/compliance/soa.py` (`KERROS_COMPLIANCE_SOA=1`) to generate
a structured draft JSON mapping selected ISO/IEC 27001:2022 themes to
in-tree KerrOS artifacts.

See also the narrower logging map:
[`iso27001-audit-logging-map.md`](iso27001-audit-logging-map.md).

| Control (sample) | Status | Artifact |
|------------------|--------|----------|
| A.8.15 Logging | implemented | `kernel/decision_log.py` |
| A.12.4 Logging and monitoring | implemented | audit chain / WORM / SIEM |
| A.8.10 Information deletion | partial | erasure ledger + crypto-shred |
| A.5.17 Authentication information | partial | OIDC RP foundation |
| A.5.15 Access control | partial | audit RBAC + IdP portal |

## Explicitly not covered

- Accredited ISO/IEC 27001 certificates of conformity  
- Production xmlsec/HSM-backed XMLDSig and XML encryption  

Foundation stubs complete through [ADR-045](../adr/ADR-045-auditor-cert-xmldsig.md);
arc freeze in [ADR-046](../adr/ADR-046-mesh-lgu-foundation-arc-complete.md).
Revisit only under a funded regulated deploy.
