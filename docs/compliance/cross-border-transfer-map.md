# Cross-border Transfers + Sealed-Cold Erasure Review (KerrOS)

**Status:** Informative foundation (ADR-026)  
**Not:** SCCs package, TIA template, or hardware WORM certification.

| Theme | Intent | KerrOS artifact |
|-------|--------|-----------------|
| Sealed-cold erasure review | Document why sealed evidence cannot be rewritten | `review_sealed_erasure` outcomes on erasure ledger ([ADR-026](../adr/ADR-026-sealed-cold-erasure-transfers.md)) |
| Transfer intent record | Log from→to region + mechanism before moving evidence | `TransferLedger` ([ADR-026](../adr/ADR-026-sealed-cold-erasure-transfers.md)) |
| Mechanism vocabulary | SCC / adequacy / consent / derogation / internal | `MECHANISMS` in `adapters/audit/transfer_ledger.py` |
| Residency tag on egress | Declare processing region | `audit_residency` ([ADR-025](../adr/ADR-025-residency-erasure-ledger.md)) |

## Explicitly not covered here

- Hardware WORM appliances / full SoA  
- Automatic byte movement / brokered transfer pipelines  
- IdP data-subject access portals  
- Executing erasure by destroying sealed cold store  

Revisit those when a funded regulated deployment specifies them.
