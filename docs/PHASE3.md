# Phase 3 — Event Infrastructure

**Status:** Implemented (foundation)  
**Trigger:** Workflow automation, local GPU inference

## Deliverables

| Component | Module | Description |
|-----------|--------|-------------|
| **Event bus** | `runtime/event_bus.py` | Typed pub/sub with history and wildcards |
| **Scheduler** | `runtime/scheduler.py` | One-shot and interval jobs |
| **Workflow engine** | `runtime/workflows.py` | DAG step execution |
| **Ollama adapter** | `adapters/llm/ollama_adapter.py` | Local LLM via OpenAI-compatible API |
| **vLLM adapter** | `adapters/llm/vllm_adapter.py` | Self-hosted vLLM inference |
| **Composite LLM** | `adapters/llm/composite_adapter.py` | Local-first with cloud fallback |

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
- `/workflows` — list registered workflows
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

## Deferred

- Distributed event mesh across nodes (C-16)
- Cron expression parsing
- Persistent workflow state / resume
- Workflow YAML definitions
