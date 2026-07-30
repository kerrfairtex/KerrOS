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

- Auditor-issued / certified evidence certificates  
- Full XMLDSig / XML encryption with production keys  

Foundation stubs: [ADR-041](../adr/ADR-041-soa-audit-saml.md),
[ADR-044](../adr/ADR-044-soa-evidence-saml-federation.md).
Revisit when a funded regulated deploy specifies certification scope.
