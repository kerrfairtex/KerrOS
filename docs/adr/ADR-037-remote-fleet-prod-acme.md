# ADR-037: Remote Fleet Orchestration + Packaged Production ACME

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-035 shipped local multi-broker fleets and a fake ACME issuance
pipeline. Remaining contract-only mesh work was *remote* fleet
orchestration across hosts and packaged production ACME via certbot /
acme.sh — without requiring live SSH or Let's Encrypt in CI.

## Decision

1. **`runtime/nats_remote_fleet.py`** — plan/apply start/stop/status
   across remote hosts via Fake / soft HTTP / soft SSH agent transports
2. **`runtime/acme_production.py`** — packaged ACME runner (fake writes
   LE-style live-dir PEMs; soft certbot / acme.sh when `allow_live`)
3. Config: `actor_mesh.supercluster.remote_fleet`,
   `actor_mesh.acme.production` (default off)

Out of scope: inventory/CMDB, Kubernetes operators, mandatory certbot in
CI, auditor-signed SoA / SAML (ADR-036 residual).

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Ansible/Terraform in-repo | Ops weight; soft agents enough |
| Hard-require certbot in tests | Breaks slim CI; FakePackagedAcme enough |

## Consequences

**Positive:** Operators can orchestrate remote fleet actions and package
certs into live-dir for ADR-029 watchers using fake or soft tools.

**Negative:** Live SSH/HTTP/certbot remain opt-in; no host provisioning.

## Revisit when

A contract funds inventory-driven orchestration, Kubernetes operators, or
fully automated production LE renewal timers.
