# ADR-013: Gated YAML Tool / LLM Workflow Actions

**Status:** Accepted  
**Date:** 2026-07-29

## Context

ADR-010 shipped declarative workflow YAML with a closed action set and deferred
tool/LLM steps. Operators want reviewable pipelines that call `LLMPort` and
`run_tool` without embedding Python — but open code exec or unrestricted tool
dispatch from YAML would bypass KerrOS guardrails.

## Decision

Extend the built-in registry with **explicit, gated** actions:

1. **`llm` / `llm_complete`** — `params.prompt` (+ optional `system`,
   `max_tokens`, `provider_hint`); templates via `{{ step_id }}`
2. **`tool`** — `params.tool` + `params.args`; always through `scope_gate`
3. **`WorkflowActionContext`** — injectable `llm_complete` / `run_tool` for
   tests; lazy `kernel.access` fallback at step runtime
4. **Allowlist** — `workflow_actions.allowed_tools` (default:
   `calc`, `skills_list`, `skill_view`, `skill_manage`); `["*"]` or
   `allow_all_tools: true` to open (still scope-gated)
5. **`allow_llm`** — can disable LLM steps without removing YAML files

No `eval`, no arbitrary imports, no shell strings as actions.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Unrestricted tool names from YAML | Too easy to smuggle deploy/offensive tools |
| Serialize Python lambdas | Unsafe / brittle (ADR-010) |
| Separate DSL for tools only | Extra surface; closed registry is enough |

## Consequences

**Positive:** Demos `demo.tool_calc` / `demo.llm_echo`; tests inject fakes;
resume still requires YAML reload.

**Negative:** New tool kinds for YAML need allowlist updates; LLM steps need a
live provider at run time.

## Revisit when

Workflows need batch tool plans or streaming LLM tokens — extend params, keep
the closed action names.
