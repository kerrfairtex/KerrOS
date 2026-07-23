# ADR-005: kerrd Service Daemon

**Status:** Accepted  
**Date:** 2026-07-23

## Context

Phase 1 delivered kernel boot, watchdog, subprocess IPC for the Code Agent, and decision logging. Phase 2 requires a runtime layer to manage long-lived services, health monitoring, and supervised restarts — the README "kerrd" milestone.

## Decision

Introduce `kerrd` as the KerrOS service daemon with:

1. **ServiceManager** — register/start/stop/monitor subprocess services
2. **ServiceBus** — in-process pub/sub for lifecycle events (not a network mesh)
3. **HealthMonitor** — aggregate kernel, services, and decision log status
4. **Kernel registration** — `service_manager` and `health_monitor` resolve via DI after boot

Default autostart service: `code-worker` (IPC-enabled subprocess runner).

## Consequences

**Positive:**
- Single entry point for runtime services (`./kerrd start`)
- Health and service status exposed to CLI (`/health`, `/services`)
- Crash restart with decision log audit trail
- Foundation for multi-service deployments without network IPC yet

**Negative:**
- In-process bus does not span machines (deferred to C-16)
- `run_daemon.py` becomes a thin shim — callers should migrate to `kerrd`

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| systemd only | Termux/mobile targets lack systemd |
| nng/socket mesh now | Over-engineered for single-node Phase 2 |
| No daemon — chat-only | Cannot supervise background workers |
