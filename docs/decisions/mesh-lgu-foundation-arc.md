# Mesh / LGU foundation arc — complete

**Status:** Complete (ADR-046)  
**Date:** 2026-07-30

The in-repo **actor mesh** and **LGU compliance** foundation programs
are complete through [ADR-045](../adr/ADR-045-auditor-cert-xmldsig.md).
See [ADR-046](../adr/ADR-046-mesh-lgu-foundation-arc-complete.md).

## In scope (shipped, default-off)

- Actor mesh through Go operator stubs, vendor CMDB/cert facades,
  apt/yum staging and remote mirror gates (ADR-012…043)
- LGU decision-log / WORM / privacy / SoA / SAML / auditor cert /
  XMLDSig foundations (ADR-017…027, 034, 036, 041, 044, 045)

## Contract-only (not pursued as soft stubs)

- Shipped Go/Helm operator images to public registries
- Vendor-issued partnership certificates
- Public apt/yum mirror publish automation
- Accredited ISO/IEC 27001 certificates of conformity
- HSM-backed xmlsec XMLDSig / XML encryption

Revisit only when a funded deploy names one of the contract-only items.
