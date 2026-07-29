# Phase 2 — Runtime

**Status:** Implemented (foundation)  
**Trigger:** Server deployment / multi-service operation

## Deliverables

| Component | Module | Description |
|-----------|--------|-------------|
| **kerrd** | `kerrd`, `runtime/kerrd.py` | Service daemon CLI |
| **Service manager** | `runtime/services.py` | Register, start, stop, supervise services |
| **Service bus** | `runtime/service_bus.py` | In-process pub/sub for lifecycle events |
| **Health monitoring** | `runtime/health.py` | Aggregate kernel + services + decision log health |
| **IPC** | `runtime/ipc.py` (P1) | JSON-line protocol for worker services |

## Usage

```bash
./kerrd start              # foreground daemon with health loop
./kerrd start --watchdog     # supervised restart on crash
./kerrd status               # JSON status
./kerrd health               # JSON health report
./kerrd restart-service --service code-worker
./kerrd stop
```

In chat:

- `/health` — runtime health summary
- `/services` — managed service states

## Default services

| Service | IPC | Autostart | Purpose |
|---------|-----|-----------|---------|
| `code-worker` | yes | yes | Isolated code execution (`agents.code.subprocess_runner`) |

## Kernel integration

Boot registers:

- `service_manager` — `ServiceManager` with default services
- `health_monitor` — `HealthMonitor`

```python
from kernel import resolve
mgr = resolve("service_manager")
health = resolve("health_monitor")
```

## Deferred (multi-node / scale triggers)

- IPC actor-mesh (nng/socket) — C-16 full
- ~~Docker server deployment — C-17~~ — foundation: [`deploy/event_mesh/`](../deploy/event_mesh/) ([ADR-011](adr/ADR-011-docker-event-mesh.md))
- pgvector → Qdrant migration — C-18
- LGU audit immutability extensions — Phase 2 governance follow-up

## Legacy

`run_daemon.py` now delegates to `kerrd start`.
