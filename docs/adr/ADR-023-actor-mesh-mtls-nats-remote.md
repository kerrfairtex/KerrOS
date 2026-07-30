# ADR-023: Actor Mesh mTLS + NATS + Remote Process Supervision Foundation

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-018/020 shipped named routes, req/reply, local heartbeats, and
`_sys.ping`. PHASE2/PHASE3 still deferred “mTLS / NATS / remote process
supervision.” Operators need optional in-process TLS for the socket
backend, a soft NATS backend, and an opt-in ServiceManager restart hook —
without hard dependencies or OTP trees.

## Decision

1. **`runtime/actor_mesh_tls.py`** — stdlib `ssl.SSLContext` builders;
   `actor_mesh.tls` (default off); wrap `SocketActorBackend` accept/dial
2. **`runtime/nats_actor_backend.py`** — soft `nats-py` backend
   (`backend: nats`); missing package → fall back to socket; in-memory
   client for CI
3. **`runtime/actor_remote_supervision.py`** — `remote_restart` +
   `process_map` (actor → ServiceManager service); wired from boot when
   supervision is enabled
4. Config/env knobs; no secrets in tree

Out of scope: production CA automation, NATS JetStream HA, full OTP
supervision trees, hard `nats`/`cryptography` deps.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Keep TLS external-only forever | Blocks lab/WAN without a proxy; stdlib SSL is enough for foundation |
| Hard-require nats-py | Breaks Termux / slim CI (same rationale as pynng) |
| Auto-restart every dead actor | Dangerous; opt-in map only |

## Consequences

**Positive:** Loopback mTLS works in tests; NATS can be selected when
installed; dead actors can restart mapped services.

**Negative:** Self-signed / check_hostname=false is common in lab; NATS
backend is broadcast-oriented (not JetStream); restart is not a
supervision tree.

## Revisit when

~~JetStream cluster failover + ACME live-dir watch~~ — **ADR-029.**
~~Supercluster topology / ACME HTTP-01 solvers~~ — **ADR-030.**
Remaining: Supercluster topology ops / ACME account+DNS-01 when funded.
