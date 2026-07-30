# Phase 3 — Event Infrastructure

**Status:** Implemented (foundation)  
**Trigger:** Workflow automation, local GPU inference

## Deliverables

| Component | Module | Description |
|-----------|--------|-------------|
| **Event bus** | `runtime/event_bus.py` | Typed pub/sub with history and wildcards |
| **Scheduler** | `runtime/scheduler.py` | One-shot, interval, and 5-field cron jobs |
| **Cron parser** | `runtime/cron.py` | Zero-dep 5-field expression → next run |
| **Workflow engine** | `runtime/workflows.py` | DAG step execution + SQLite run persistence/resume |
| **Workflow YAML** | `runtime/workflow_yaml.py` | Declarative defs + gated `llm`/`tool` actions (ADR-010/013) |
| **Workflow run store** | `runtime/workflow_store.py` | `data/workflows/runs.db` checkpoints |
| **Ollama adapter** | `adapters/llm/ollama_adapter.py` | Local LLM via OpenAI-compatible API |
| **vLLM adapter** | `adapters/llm/vllm_adapter.py` | Self-hosted vLLM inference |
| **Local LLM probe** | `adapters/llm/local_llm_probe.py` | Health probes for Ollama / vLLM (C-19) |
| **Ollama Docker** | `deploy/ollama/` | Loopback Ollama sidecar + `scripts/local_llm_docker.sh` |
| **Composite LLM** | `adapters/llm/composite_adapter.py` | Local-first with cloud fallback |
| **OmniRoute telemetry** | `adapters/llm/omniroute_telemetry.py` | Parse `X-OmniRoute-*` cost/usage headers → `omniroute.usage` EventBus events |
| **Event mesh** | `runtime/event_mesh.py` | LocalEventMesh + Null/File/HTTP stubs (ADR-008) |
| **Mesh broker** | `runtime/event_mesh_broker.py` | Durable SQLite broker + file/SQL peer discovery (ADR-009) |
| **Mesh HTTP** | `runtime/event_mesh_http.py` | Ingest listener for Docker multi-node (ADR-011) |
| **Mesh auth** | `runtime/mesh_auth.py` | Shared-secret tokens for HTTP + actor mesh (ADR-014) |

## Usage

### Event bus

```python
from kernel import boot, resolve
boot()
bus = resolve("event_bus")
bus.subscribe("workflow.completed", lambda e: print(e.payload))
bus.publish("custom.topic", {"key": "value"})
```

### Scheduler

```python
sched = resolve("scheduler")
sched.schedule_interval("heartbeat", 60.0)
sched.schedule_once("delayed", 5.0, callback=lambda: print("fired"))
```

### Workflows

```python
from runtime.workflows import WorkflowDefinition, WorkflowStep

engine = resolve("workflow_engine")
engine.register(WorkflowDefinition(
    name="demo",
    steps=[
        WorkflowStep("a", action=lambda ctx: "hello"),
        WorkflowStep("b", action=lambda ctx: ctx["a"] + " world", depends_on=["a"]),
    ],
))
run = engine.run("demo")
```

### Local LLM (C-19)

Adapters already implement `LLMPort`. Ops foundation: loopback Ollama compose +
HTTP probes wired into `HealthMonitor` ([`ADR-016`](adr/ADR-016-local-llm-ops.md)).

```bash
./scripts/local_llm_docker.sh up
./scripts/local_llm_docker.sh pull llama3.2
./scripts/local_llm_docker.sh probe

export KERROS_LOCAL_LLM=1          # try Ollama → vLLM before cloud
export KERROS_LLM_PROVIDER=ollama  # force provider
export OLLAMA_ENDPOINT=http://127.0.0.1:11434/v1
export OLLAMA_MODEL=llama3.2
export VLLM_ENDPOINT=http://127.0.0.1:8000/v1
export VLLM_MODEL=meta-llama/Llama-3.2-3B-Instruct
```

vLLM is bring-your-own GPU endpoint (same `/v1/models` probe). Or pass
`provider_hint` in `llm_complete()` / `LLMPort.complete()`.

## CLI

- `/events [n]` — recent event bus events
- `/schedule` — list jobs; `/schedule cron <name> <expr>`; `/schedule cancel <id>`
- `/workflows` — list; `/workflows run <name>`; `/workflows reload`; `/workflows runs [n]`; `/workflows resume <id>`
- `/llm` — provider availability status

## Kernel integration

Boot registers:

- `event_bus` — `EventBus`
- `scheduler` — `Scheduler` (autostarted)
- `workflow_engine` — `WorkflowEngine`
- `llm_port` — `CompositeLLMAdapter` (replaces direct `MultiAPIAdapter`)

## Relationship to Phase 2

`ServiceBus` remains for service lifecycle events (`service.crashed`, etc.).
`EventBus` is the general-purpose infrastructure for workflows, scheduler,
and cross-component reactions.

### OmniRoute cost/usage events

Non-streaming OmniRoute responses carry `X-OmniRoute-*` headers (cost, tokens,
model, provider, latency, cache). `OpenAICompatClient` (provider `omniroute`)
publishes them on the kernel EventBus as topic `omniroute.usage` without
changing the `LLMPort.complete() -> str` contract. Inspect via `/events`.

### LLM provider resilience (P6)

`CompositeLLMAdapter` gates each provider with a KerrOS-native 3-layer model
inspired by OmniRoute (not a port of their per-key catalog):

1. **Circuit breaker** — open after `failure_threshold` consecutive failures
2. **Cooldown** — after `cooldown_s`, one half-open probe is allowed
3. **Lockout** — after `lockout_opens` opens, provider is locked for `lockout_s`

Config: `llm_resilience` in `config.json` / `kernel/config.py` defaults.
CLI: `/llm` shows circuit state; `/llm reset [provider]` clears lockout.
Events: `llm.circuit.*` on the kernel EventBus.

## Deferred

- ~~Authenticated WAN / full actor orchestrator~~ — foundation in Phase 2 ([ADR-018](adr/ADR-018-actor-mesh-orchestrator-foundation.md) + [ADR-020](adr/ADR-020-actor-mesh-supervision-foundation.md)); mTLS / NATS / remote process supervision still deferred
- In-repo `deploy/vllm/` GPU compose (probe/env only until a funded GPU host)

## Workflow YAML definitions

Declarative workflows live under `config/workflows/*.yaml` (override with
`workflow_yaml_dir`). Built-in actions: `set`/`echo`, `get`, `template`,
`merge`, `publish`, `noop`, `assert_eq`, **`llm`**, **`tool`**. Boot auto-loads
the directory; CLI `/workflows reload` re-registers. See
[`ADR-010`](adr/ADR-010-workflow-yaml.md) and
[`ADR-013`](adr/ADR-013-workflow-yaml-tool-llm.md).

```yaml
name: demo.tool_calc
steps:
  - id: expr
    action: set
    params: { value: "2+2" }
  - id: result
    action: tool
    depends_on: [expr]
    params: { tool: calc, args: "{{ expr }}" }
```

Tool steps use `workflow_actions.allowed_tools` (default: calc / skills_*);
`scope_gate` still applies. LLM steps need a configured provider at run time.

## Event mesh foundation

`LocalEventMesh` bridges in-process buses and optionally forwards via a
`EventMeshTransport` (null / file JSONL / HTTP stub / durable SQLite). Enable with:

```json
"event_mesh": {
  "enabled": true,
  "node_id": "node-a",
  "transport": "durable",
  "broker_db": "data/event_mesh/broker.db"
}
```

or `KERROS_EVENT_MESH=1`. Peer discovery: file heartbeats under `discovery_dir`
(auto-on for durable) + `mesh_peers` in the broker DB. Ingest remote events with
`mesh.poll()` (durable/file) or HTTP `/mesh/ingest` (Docker).

### Docker multi-node (C-17)

```bash
./scripts/event_mesh_docker.sh up
./scripts/event_mesh_docker.sh verify
```

See [`deploy/event_mesh/`](../deploy/event_mesh/) and
[`ADR-011`](adr/ADR-011-docker-event-mesh.md). Set
`KERROS_EVENT_MESH_TOKEN` for authenticated POSTs ([`ADR-014`](adr/ADR-014-authenticated-mesh.md)).
Also: [`ADR-008`](adr/ADR-008-event-mesh-foundation.md),
[`ADR-009`](adr/ADR-009-event-mesh-transport.md).

## Cron scheduling

5-field cron (`m h dom mon dow`) via `runtime/cron.py` — no extra dependencies.

```python
sched = resolve("scheduler")
sched.schedule_cron("hourly", "0 * * * *", callback=lambda: "tick")
```

CLI: `/schedule cron <name> <expr>`, `/schedule cancel <id>`.

## Persistent workflow state

Runs checkpoint to SQLite (`data/workflows/runs.db` by default) after each step.
`WorkflowEngine.list_runs()` / `resume(run_id)` reload state across process
restarts. Step **callables** are not serialized — the workflow definition must
be re-registered before resume. CLI: `/workflows runs`, `/workflows resume <id>`.
