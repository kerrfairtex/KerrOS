# Phase 3 — Event Infrastructure

**Status:** Implemented (foundation)  
**Trigger:** Workflow automation, local GPU inference

## Deliverables

| Component | Module | Description |
|-----------|--------|-------------|
| **Event bus** | `runtime/event_bus.py` | Typed pub/sub with history and wildcards |
| **Scheduler** | `runtime/scheduler.py` | One-shot and interval jobs |
| **Workflow engine** | `runtime/workflows.py` | DAG step execution + SQLite run persistence/resume |
| **Workflow run store** | `runtime/workflow_store.py` | `data/workflows/runs.db` checkpoints |
| **Ollama adapter** | `adapters/llm/ollama_adapter.py` | Local LLM via OpenAI-compatible API |
| **vLLM adapter** | `adapters/llm/vllm_adapter.py` | Self-hosted vLLM inference |
| **Composite LLM** | `adapters/llm/composite_adapter.py` | Local-first with cloud fallback |
| **OmniRoute telemetry** | `adapters/llm/omniroute_telemetry.py` | Parse `X-OmniRoute-*` cost/usage headers → `omniroute.usage` EventBus events |

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

### Local LLM

Set environment variables:

```bash
export KERROS_LOCAL_LLM=1          # try Ollama → vLLM before cloud
export KERROS_LLM_PROVIDER=ollama  # force provider
export OLLAMA_ENDPOINT=http://localhost:11434/v1
export OLLAMA_MODEL=llama3.2
export VLLM_ENDPOINT=http://localhost:8000/v1
export VLLM_MODEL=meta-llama/Llama-3.2-3B-Instruct
```

Or pass `provider_hint` in `llm_complete()` / `LLMPort.complete()`.

## CLI

- `/events [n]` — recent event bus events
- `/schedule` — list scheduled jobs
- `/workflows` — registered workflows; `/workflows runs [n]`; `/workflows resume <id>`
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

- Distributed event mesh across nodes (C-16)
- Cron expression parsing
- Workflow YAML definitions

## Persistent workflow state

Runs checkpoint to SQLite (`data/workflows/runs.db` by default) after each step.
`WorkflowEngine.list_runs()` / `resume(run_id)` reload state across process
restarts. Step **callables** are not serialized — the workflow definition must
be re-registered before resume. CLI: `/workflows runs`, `/workflows resume <id>`.
