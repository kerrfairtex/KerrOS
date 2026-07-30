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
| **Actor mesh** | `runtime/actor_mesh.py` | Optional nng/socket ServiceBus fanout (C-16 / ADR-012) |
| **Decision log (LGU)** | `kernel/decision_log.py` | Hash-chained append-only audit + JSONL export (ADR-017) |

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
- `/decisions` — recent audit entries; `verify` / `export [path]` (ADR-017)

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

## Actor mesh (C-16)

Optional cross-process `ServiceBus` fanout via stdlib TCP or pynng Bus0:

```json
"actor_mesh": {
  "enabled": true,
  "backend": "nng",
  "listen": "tcp://127.0.0.1:9091",
  "peers": ["tcp://127.0.0.1:9092"]
}
```

or `KERROS_ACTOR_MESH=1`. Use `ActorMesh.publish` for remote fanout. See
[`ADR-012`](adr/ADR-012-actor-mesh.md). Optional dep: `requirements-optional.txt`.

## Deferred (multi-node / scale triggers)

- Full actor orchestrator / authenticated WAN mesh (beyond ADR-012 foundation)
- ~~Docker server deployment — C-17~~ — foundation: [`deploy/event_mesh/`](../deploy/event_mesh/) ([ADR-011](adr/ADR-011-docker-event-mesh.md))
- ~~pgvector → Qdrant migration — C-18~~ — optional Qdrant sidecar + SQLite backfill ([ADR-015](adr/ADR-015-qdrant-optional-vector-store.md), [`deploy/qdrant/`](../deploy/qdrant/))
- ~~Self-hosted LLM ops — C-19~~ — Ollama compose + probes ([ADR-016](adr/ADR-016-local-llm-ops.md), [`deploy/ollama/`](../deploy/ollama/)); see Phase 3
- ~~LGU audit immutability extensions~~ — foundation: hash chain + JSONL export + port audit hooks ([ADR-017](adr/ADR-017-decision-log-tamper-evidence-export.md)); WORM/RBAC/retention deferred until funded LGU contract

## Legacy

`run_daemon.py` now delegates to `kerrd start`.
