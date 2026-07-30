# ADR-061: Subagent Delegation (Deferred Soft Foundation)

**Status:** Accepted (deferred implementation)  
**Date:** 2026-07-30

## Context

Hermes can spawn up to three concurrent child agents with isolated
contexts. KerrOS already has multiple userspace agents, but the REPL is
serialized. Concurrent delegation is the most invasive Hermes behavior and
fits poorly on ~3.7GB phone-class hosts.

## Decision

**Defer live concurrent subagents.** Document the intended contract only:

- Cap concurrency at 2 (not 3) when funded.
- Restricted tool subsets; never looser than parent scope_gate / deploy arm.
- Results converge through Planner.

No `delegate_task` runtime ships in this change set — Soft/Fake only if a
planner stub is added later under an explicit feature flag.

## Consequences

**Positive:** Avoids unstable parallelism on constrained hardware.

**Negative:** Complex tasks remain serialized until a funded host lands.

## Revisit when

VPS/GPU headroom exists and items ADR-056…060 are stable in production use.
