# ADR-004: P0 Kernel Contract

**Status:** Accepted  
**Date:** 2026-07-23  
**Deciders:** KerrOS engineering

## Context

KerrOS README defines P0 as kernel foundation: contract, boot lifecycle, dependency injection, and configuration system. The codebase had fragmented config loading, no formal boot sequence, and singletons created via lazy imports across `core/` and `cli/`.

Engineering backlog v0.2 (KOS-004+) planned ports/adapters but assumed a kernel namespace without defining the boot or DI contract.

## Decision

Establish a minimal P0 kernel in `kernel/` with four modules:

1. **`contract.py`** — `BootPhase`, service name constants, kernel error types
2. **`config.py`** — `KernelConfig` with base/workspace/scope resolution
3. **`container.py`** — register/resolve DI container
4. **`boot.py`** — deterministic boot/shutdown lifecycle and global singleton

Default boot registers:
- `config` → `KernelConfig`
- `router` → `kernel.router` dispatch functions
- `tool_port` → `ClawToolAdapter`
- `llm_port` → `MultiAPIAdapter`

`cli/chat.py` calls `kernel.boot()` at session start.

## Consequences

**Positive:**
- Single entry point for runtime initialization
- Config paths resolved once, consistently
- Ports can be swapped by re-registering in boot hooks
- Foundation for KOS-008 (decision log) and KOS-011 (watchdog)

**Negative:**
- Parallel config path (`core/config.py` still exists; kernel wraps it)
- `kernel/router.py` remains thick until further refactor
- Naming collision with `CompletionRuntimeKernel` persists (KOS-015)

## Alternatives considered

1. **Extend `core/completion_runtime_kernel.py`** — rejected; wrong abstraction layer
2. **Full DI framework** — rejected; over-engineered for P0
3. **Config-only unification without boot** — rejected; doesn't address lifecycle

## Compliance

Boot order matches backlog: config → services → ports → ready. Decision log and watchdog attach in P1 (KOS-008, KOS-011) without changing the contract surface.
