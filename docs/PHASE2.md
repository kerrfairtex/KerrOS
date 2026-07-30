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
| **Actor mesh** | `runtime/actor_mesh.py` | Optional nng/socket fanout + req/reply + supervision (C-16 / ADR-012/018/020) |
| **Decision log (LGU)** | `kernel/decision_log.py` | ADR-017..026 (hash chain → residency/erasure → sealed-cold review + transfers) |

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
- `/decisions` — `verify` / `export` / `seal` / `retain` / `whoami` / `privacy` / `residency` / `erasure` / `erasure-review` / `transfer` (ADR-017..026)

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

## Actor mesh (C-16 / ADR-018 / ADR-020)

Optional cross-process `ServiceBus` fanout via stdlib TCP or pynng Bus0,
plus named actors, routes, request/reply, runtime peer dial, and local
supervision:

```json
"actor_mesh": {
  "enabled": true,
  "backend": "socket",
  "listen": "tcp://127.0.0.1:9091",
  "peers": ["tcp://127.0.0.1:9092"],
  "routes": {"echo": "node-b"},
  "auth_token": "",
  "auth_required_non_loopback": false,
  "supervision": {
    "enabled": true,
    "ttl_s": 30,
    "suspect_after_s": 15,
    "heartbeat_interval_s": 0,
    "auto_register_ping": true
  }
}
```

or `KERROS_ACTOR_MESH=1`. Use `ActorMesh.publish` for fanout,
`register` / `request` for RPC, `add_peer` for late WAN join,
`supervisor.beat` / `sweep` / `ping` for liveness. Auth via
[`ADR-014`](adr/ADR-014-authenticated-mesh.md) (`KERROS_ACTOR_MESH_TOKEN`).
See [`ADR-012`](adr/ADR-012-actor-mesh.md),
[`ADR-018`](adr/ADR-018-actor-mesh-orchestrator-foundation.md),
[`ADR-020`](adr/ADR-020-actor-mesh-supervision-foundation.md).
Optional dep: `requirements-optional.txt`.

## Deferred (multi-node / scale triggers)

- ~~Full actor orchestrator / authenticated WAN mesh~~ — foundation: named routes + req/reply + `add_peer` + non-loopback token gate ([ADR-018](adr/ADR-018-actor-mesh-orchestrator-foundation.md)); local supervision ([ADR-020](adr/ADR-020-actor-mesh-supervision-foundation.md)); mTLS/NATS/remote restart ([ADR-023](adr/ADR-023-actor-mesh-mtls-nats-remote.md)); JetStream HA / OTP trees still deferred
- ~~Docker server deployment — C-17~~ — foundation: [`deploy/event_mesh/`](../deploy/event_mesh/) ([ADR-011](adr/ADR-011-docker-event-mesh.md))
- ~~pgvector → Qdrant migration — C-18~~ — optional Qdrant sidecar + SQLite backfill ([ADR-015](adr/ADR-015-qdrant-optional-vector-store.md), [`deploy/qdrant/`](../deploy/qdrant/))
- ~~Self-hosted LLM ops — C-19~~ — Ollama compose + probes ([ADR-016](adr/ADR-016-local-llm-ops.md), [`deploy/ollama/`](../deploy/ollama/)); see Phase 3
- ~~LGU audit immutability extensions~~ — hash chain + JSONL ([ADR-017](adr/ADR-017-decision-log-tamper-evidence-export.md)); WORM/retention ([ADR-019](adr/ADR-019-decision-log-worm-retention.md)); RBAC/SIEM ([ADR-021](adr/ADR-021-decision-log-rbac-siem.md)); Object Lock soft + ISO map ([ADR-022](adr/ADR-022-decision-log-object-lock-iso-map.md)); jurisdiction privacy egress ([ADR-024](adr/ADR-024-jurisdiction-privacy-foundation.md)); residency + erasure ledger ([ADR-025](adr/ADR-025-residency-erasure-ledger.md)); sealed-cold review + transfers ([ADR-026](adr/ADR-026-sealed-cold-erasure-transfers.md)); hardware WORM appliance / auto-pipelines still deferred

## Legacy

`run_daemon.py` now delegates to `kerrd start`.
