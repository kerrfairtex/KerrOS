# P0 Kernel Foundation — Kernel Contract

**Status:** P0 (active development)  
**Version:** 0.1.0-draft

## Purpose

The kernel contract is the stable boundary between KerrOS coordination services and everything else (ports, adapters, agents, CLI). Components outside `kernel/` must interact with the system through this contract — not by importing implementation details directly.

## P0 pillars

| Pillar | Module | Responsibility |
|--------|--------|----------------|
| Kernel contract | `kernel/contract.py` | Lifecycle phases, service names, error types |
| Configuration | `kernel/config.py` | Typed config load, workspace/base/scope paths |
| Dependency injection | `kernel/container.py` | Register and resolve kernel services |
| Boot lifecycle | `kernel/boot.py` | Deterministic INIT → READY → SHUTDOWN |

## Boot lifecycle

```
INIT → CONFIG → SERVICES → PORTS → READY
                              ↓
                         SHUTDOWN → INIT
```

| Phase | What happens |
|-------|--------------|
| `INIT` | Kernel created, container empty |
| `CONFIG` | Load `.env` + `config.json`, resolve workspace |
| `SERVICES` | Register config + router dispatch |
| `PORTS` | Register default LLM and tool port adapters |
| `READY` | Kernel accepts `resolve()` calls |
| `SHUTDOWN` | Clear container, reset to INIT |

### Boot API

```python
from kernel import boot, get_kernel, resolve, shutdown

kernel = boot()
config = resolve("config")
tool_port = resolve("tool_port")
router = resolve("router")

shutdown()
```

## Registered services

| Name | Type | Description |
|------|------|-------------|
| `config` | `KernelConfig` | Runtime configuration snapshot |
| `decision_log` | `DecisionLog` | Append-only audit log (KOS-008) |
| `router` | `dict` | `detect_tool`, `run_tool`, `detect_domain` |
| `llm_port` | `LLMPort` | `MultiAPIAdapter` (default) |
| `tool_port` | `ToolPort` | `ClawToolAdapter` (filesystem/exec) |
| `memory_port` | `MemoryPort` | `RagStoreAdapter` (KOS-006) |
| `dispatch_port` | `DispatchPort` | `RouterAdapter` (KOS-007) |

## Configuration

Environment variables (highest priority for paths):

| Variable | Purpose |
|----------|---------|
| `KERROS_BASE` / `OFFLINE_AI_BASE` | Repo/install root |
| `KERROS_WORKSPACE` | Agent workspace for file/exec tools |
| `KERROS_PROJECT_ROOT` | Alias for workspace |

Load order for values: `.env` overrides → `config.json` base → env var overrides (via `core/config.py`).

## Dependency injection rules

1. **Register during boot only** — services are wired in `kernel/boot.py` or explicit boot hooks.
2. **Resolve after READY** — `resolve(name)` raises `KernelNotReadyError` before boot completes.
3. **Singleton by default** — ports and config are cached; pass `singleton=False` for transient factories.
4. **No circular imports** — factories are lazy; adapters import inside factory functions.
5. **Port access facade** — callers use `kernel.access` (`detect_tool`, `memory_query`, `llm_complete`) for kernel-first resolution with direct fallback (KOS-014).

## Error types

| Exception | When |
|-----------|------|
| `KernelNotReadyError` | `resolve()` before boot |
| `KernelBootError` | Boot sequence failure |
| `ServiceNotFoundError` | Unknown service name |
| `ServiceAlreadyRegisteredError` | Duplicate registration |

## Stability guarantees (P0)

**Stable (will not break without ADR):**
- `BootPhase` enum values
- Service name constants (`SERVICE_*`)
- `boot()`, `shutdown()`, `resolve()`, `get_kernel()`
- `KernelConfig` fields: `base`, `workspace`, `scope_path`, `get()`, `require()`

**Unstable (may change in P1+):**
- Default port adapter choices
- Additional registered services
- Watchdog / decision log integration (KOS-008, KOS-011)

## What is NOT the kernel

- `core/completion_runtime_kernel.py` — completion pipeline coordinator (userspace)
- `kernel/router.py` — tool dispatch (will be thinned; business logic moves to adapters)
- `agents/*` — userspace agents
- `tools/*` — capability implementations

## Related ADRs

- [ADR-004](adr/ADR-004-kernel-contract.md) — Kernel contract decision record
