# ADR-010: Declarative Workflow YAML Definitions

**Status:** Accepted  
**Date:** 2026-07-29

## Context

Phase 3 shipped a Python `WorkflowEngine` with DAG steps as callables. Resume
requires re-registering definitions because callables are not SQLite-serializable.
PHASE3 deferred “Workflow YAML definitions”. Operators need versionable,
reviewable workflows without embedding Python in every deploy.

## Decision

Ship a **closed action set** loaded from YAML:

1. `runtime/workflow_yaml.py` — parse/register `*.yaml` → `WorkflowDefinition`
2. Built-ins only: `set`/`echo`, `get`, `template`, `merge`, `publish`, `noop`,
   `assert_eq` (no `eval` / arbitrary imports)
3. Boot loads `config/workflows/` (`workflow_yaml_dir`); CLI `/workflows reload`
   and `/workflows run <name>`
4. Catalog JSON still records action **names** via `__name__` on generated fns

Arbitrary Python step bodies and shell/tool actions stay out of YAML for now.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Serialize Python callables | Unsafe / brittle |
| Full scripting (Jinja+exec) | Too much attack surface for chat REPL |
| Only keep JSON catalog | Catalog is metadata; cannot rehydrate actions |

## Consequences

**Positive:** Demo and assert workflows ship as data; resume works after boot
reload of the same YAML.

**Negative:** New step kinds need a code change to the built-in registry.
Tool/LLM steps remain Python-registered.

## Revisit when

A product need for tool-port or LLM steps in YAML appears — extend the
built-in registry with explicit, gated action names rather than open code exec.
