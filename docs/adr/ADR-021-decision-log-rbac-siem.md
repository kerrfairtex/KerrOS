# ADR-021: Decision Log RBAC + SIEM Forwarder (LGU foundation)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-017/019 shipped hash-chained evidence, JSONL export, software-WORM,
and retention. KOS-013 still deferred role-based log access and SIEM push.
Operators need a thin gate and optional forwarder without OIDC, Splunk
agents, mTLS, or hardware WORM.

## Decision

1. **`audit_rbac`** — default off; token → `reader` | `operator` | `admin`
   (constant-time compare, ADR-014 style). Gates read/verify/export/seal/
   retain/purge at CLI/scripts/adapter entrypoints. Does **not** gate
   `DecisionLog.record()`.
2. **`audit_siem`** — default off; best-effort JSON forward on `record`
   and successful seal (`webhook` POST or `syslog` UDP). Failures never
   fail the audit write path.
3. Env: `KERROS_AUDIT_TOKEN`, `KERROS_AUDIT_RBAC*`, `KERROS_AUDIT_SIEM*`.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| OIDC / LDAP | Overbuilt for Termux/single-operator installs |
| Gate every `record()` by role | Breaks scope_gate / tool audit hooks |
| Kafka / Splunk SDK | Heavy deps; webhook/syslog enough |

## Consequences

**Positive:** Evidence ops can be role-gated; SOC can receive JSON events
when enabled.

**Negative:** Token map is shared-secret only; SIEM delivery is best-effort
with no retry queue.

## Revisit when

~~Object Lock soft path + ISO audit map~~ — **ADR-022.**
An LGU contract funds IdP integration, durable SIEM pipelines, or a
hardware WORM appliance / full SoA.
