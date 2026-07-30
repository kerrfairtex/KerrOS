# ADR-020: Actor Mesh Supervision Foundation

**Status:** Accepted  
**Date:** 2026-07-30

## Context

ADR-018 shipped named actors, routes, and request/reply. PHASE2 still
deferred “mTLS / NATS / remote supervision.” Operators need local actor
liveness without adopting a broker or in-process TLS (TLS stays an
external proxy per ADR-014/018).

## Decision

1. Add `runtime/actor_supervision.py` — `ActorSupervisor` with beat / sweep /
   liveness table (`alive` → `suspect` → `dead` by TTL)
2. Optional `"_sys.ping"` handler auto-registered on mesh attach
3. `ActorSupervisor.ping` reuses `ActorMesh.request` (no new transport)
4. `on_dead` restart hook is a callable stub only (no process spawn)
5. Config `actor_mesh.supervision` (default `enabled: false`);
   `heartbeat_interval_s: 0` means explicit `sweep` only (CI-friendly)

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| In-process mTLS | ADR-018: TLS external |
| NATS / Redis broker | Heavy dep; socket/nng + token already exist |
| Wire hook → ServiceManager.restart by default | Operator choice; keep foundation thin |

## Consequences

**Positive:** Local actors can be observed; remote ping works over existing
routes; default boot unchanged.

**Negative:** No remote process supervision tree; dead actors are not
auto-restarted unless the operator supplies `on_dead`.

## Revisit when

~~mTLS / NATS / remote process restart hook~~ — **ADR-023.**
~~JetStream soft / OTP local tree / CA reload~~ — **ADR-028.**
~~JetStream cluster failover + ACME watch~~ — **ADR-029.**
~~Supercluster topology / ACME HTTP-01~~ — **ADR-030.**
Remaining: richer OTP strategies when funded.
