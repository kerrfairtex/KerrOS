# KerrOS Engineering Backlog
*Architectural decomposition of Source of Truth v0.2 → implementation roadmap. No production code included — planning artifact only.*

---

## 1. Component Inventory

| ID | Component | Type | Source (v0.2 §) | Existing / New |
|---|---|---|---|---|
| C-01 | `router.py` dispatch | Kernel | §0, §2 | Existing — currently at `tools/router.py` per repo scan |
| C-02 | `LLMPort` | Interface | §0, §2 | New |
| C-03 | `LLMPort` adapter over `multi_api.py` | Adapter | §2 | `multi_api.py` existing, adapter new |
| C-04 | `MemoryPort` | Interface | §0, §2 | New |
| C-05 | `MemoryPort` adapter over `store.py` (RAG) | Adapter | §2 | `store.py` existing, adapter new |
| C-06 | `ToolPort` | Interface | §0, §2 | New |
| C-07 | `ToolPort` adapter over `router.py` | Adapter | §0, §2 | New |
| C-08 | Watchdog process | Runtime/Kernel | §0, §1 | New — wraps `run_daemon.py` |
| C-09 | Code Agent subprocess isolation | Runtime | §1 | Modifies existing Code Agent |
| C-10 | Kernel↔Code-Agent IPC channel | Runtime | §1 (implied) | New |
| C-11 | scope_gate decision log | Storage/Event Sourcing | §0, §4 | New — SQLite append-only |
| C-12 | verify_identity / verify_business audit trail | Storage/Event Sourcing | §4 | Existing `verify_*` logic; audit wiring new |
| C-13 | ADR template + ADR-001..003 | Documentation | §3 | New |
| C-14 | Knowledge/Security/Research/Planner/Reflection/Document Agents | Userspace agents | §0 | Existing — no kernel dependency change required |
| C-15 | LGU/audit-grade scope decision | Governance artifact | §5 | Accepted general-purpose (KOS-013); LGU foundation ADR-017 (hash chain + JSONL export) |
| C-16 | IPC actor-mesh (nng/socket) | Runtime | §1 Phase 2 | Foundation — ADR-012 + orchestrator ADR-018 + supervision ADR-020 |
| C-17 | Docker (server-side) | Deployment | §1 Phase 2 | Foundation — ADR-011 (`deploy/event_mesh/`) |
| C-18 | pgvector → Qdrant migration | Storage | §3, §6 Phase 2 | Foundation — ADR-015 (`deploy/qdrant/`, optional hybrid sidecar) |
| C-19 | Self-hosted models via vLLM/Ollama | Adapter (behind LLMPort) | §6 Phase 3 | Foundation — ADR-016–054 (offline combo A–E incl. LiteLLM/llama.cpp gateway soft) |

**Missing specifications flagged:** exact current path of `scope_gate.py`, `store.py`, and `multi_api.py` were not confirmed in prior repo scans — each Phase-1 issue below that touches these must begin with a path-confirmation step before editing.

---

## 2. Dependency Graph

```
ADR template ─┬─> ADR-001 (Groq primary)
              ├─> ADR-002 (chunking)
              └─> ADR-003 (scope_gate fail-closed)
                        (no code dependency — parallel track, do anytime)

Kernel package scaffold (C-01 relocation)
      │
      ├──> LLMPort interface ──> LLMPort adapter (multi_api.py)
      ├──> MemoryPort interface ──> MemoryPort adapter (store.py)
      ├──> ToolPort interface ──> ToolPort adapter (router.py)
      │
      ├──> Watchdog (C-08) ──> Code Agent subprocess isolation (C-09) ──> IPC channel (C-10)
      │
      └──> Decision log schema (C-11) ──┬──> Wire scope_gate → log
                                          └──> Wire verify_identity/verify_business → log

LGU/audit-grade decision (C-15) ──> gates Phase 2 MemoryPort/ToolPort extensions only
                                     (does not block any Phase 1 item)
```

**Build order:** ADRs (parallel, no deps) → Kernel scaffold → Ports (parallel with each other) → Decision log → wiring → Watchdog → Code Agent isolation → IPC.
**Initialization order (runtime):** decision log opens first (so nothing else logs to a nonexistent store) → kernel/router loads → Ports register their adapters → watchdog attaches → agents come up last and register with router.
**Testing order:** unit test each Port interface with a mock adapter before wiring the real adapter; integration-test decision log writes before wiring scope_gate to it; test watchdog restart behavior in isolation before adding Code Agent subprocess.
**Deployment order:** N/A for Phase 1 (single device). Becomes relevant only at Phase 2 trigger.

---

## 3. Repository Map

```
kernel/
├── __init__.py
├── router.py            # relocated from tools/router.py, thin dispatch only
├── watchdog.py           # new — wraps run_daemon.py
└── decision_log.py       # new — event-sourced SQLite log

ports/
├── llm_port.py            # LLMPort interface (ABC/Protocol)
├── memory_port.py         # MemoryPort interface
└── tool_port.py           # ToolPort interface

adapters/
├── llm/
│   └── multi_api_adapter.py   # wraps existing multi_api.py, implements LLMPort
├── memory/
│   └── rag_store_adapter.py   # wraps existing store.py, implements MemoryPort
└── tools/
    └── router_adapter.py      # wraps kernel/router.py, implements ToolPort

agents/                  # unchanged — Knowledge, Security, Code, Research, Planner, Reflection, Document
├── code/
│   └── subprocess_runner.py   # new — isolates Code Agent execution
└── ...

runtime/
└── ipc.py                 # new — kernel↔Code Agent subprocess channel

security/
└── scope_gate.py           # existing, location to confirm — gains decision_log calls

tests/
├── ports/
├── adapters/
├── kernel/
└── runtime/

docs/
└── adr/
    ├── ADR-TEMPLATE.md
    ├── ADR-001-groq-primary.md
    ├── ADR-002-rag-chunking.md
    └── ADR-003-scope-gate-fail-closed.md
```

`tools/router.py` becomes a deprecation shim (`from kernel.router import *`) rather than being deleted outright, to avoid breaking existing imports across the agents in one PR.

---

## 4. Engineering Roadmap

**Phase 1 — now, unblocked.** All items below are actionable immediately; this is the only phase with fully specified GitHub issues (§5). Producing detailed issues for Phase 2/3 now would itself violate KerrOS's milestone-driven-evolution principle — see §6 Architecture Validation.

**Phase 2 — trigger: first paying use of a rented server.** Full IPC mesh (only if running 2+ machines), Docker server-side, pgvector→Qdrant if RAG scale demands it. Decompose into issues only once triggered.

**Phase 3 — trigger: JOTHAM revenue funds a GPU.** Self-hosted models via vLLM/Ollama behind `LLMPort` — adapters + Ollama ops (ADR-016) + soft vLLM kit (ADR-048) + soft residuals (ADR-049) landed; production edge TLS, multi-node HA, and automated weight provision remain contract-gated.

---

## 5. GitHub Issue Backlog (Phase 1 — fully specified)

### KOS-001 — Add ADR template and ADR-001 (Groq primary in fallback chain)
- **Purpose:** Establish the ADR practice and document the existing, undocumented decision to make Groq primary in the multi-API fallback chain.
- **Background:** v0.2 §3 — ADRs adopted for expensive-to-reverse decisions only; this one already exists in code but not in writing.
- **Files involved:** none (read multi_api.py for context)
- **New files:** `docs/adr/ADR-TEMPLATE.md`, `docs/adr/ADR-001-groq-primary.md`
- **Existing files to modify:** none
- **Implementation requirements:** Template sections: Context / Decision / Consequences, one page max. ADR-001 documents why Groq is first in the chain (cost, latency, or availability — confirm actual reason with whoever set it before writing).
- **Acceptance criteria:** Both files exist, ADR-001 reflects the real historical reason, not a guessed one.
- **Definition of Done:** Merged PR, no code changes, reviewed by Kerr.
- **Dependencies:** none
- **Estimated complexity:** XS (docs only)
- **Suggested labels:** `documentation`, `phase-1`, `adr`
- **Suggested milestone:** Phase 1

### KOS-002 — ADR-002: RAG chunking strategy (120-word / 30-overlap)
- **Purpose:** Document the reasoning behind the existing chunking parameters.
- **Background:** v0.2 §3.
- **New files:** `docs/adr/ADR-002-rag-chunking.md`
- **Implementation requirements:** Confirm the 120/30 figures against current `store.py` config before writing — do not assume they're still accurate.
- **Acceptance criteria:** ADR matches actual current chunking code.
- **Definition of Done:** Merged, reviewed.
- **Dependencies:** none
- **Estimated complexity:** XS
- **Suggested labels:** `documentation`, `phase-1`, `adr`
- **Suggested milestone:** Phase 1

### KOS-003 — ADR-003: scope_gate fail-closed + arm/disarm design
- **Purpose:** Document the safety-critical reasoning behind scope_gate's default-deny and timed-arm behavior.
- **New files:** `docs/adr/ADR-003-scope-gate-fail-closed.md`
- **Implementation requirements:** Describe fail-closed default, arm/disarm window mechanics, and what happens on watchdog crash (should default back to disarmed).
- **Acceptance criteria:** Reviewed against actual `scope_gate.py` behavior, not assumed behavior.
- **Definition of Done:** Merged.
- **Dependencies:** none (can run parallel to code work)
- **Estimated complexity:** S
- **Suggested labels:** `documentation`, `security`, `phase-1`, `adr`
- **Suggested milestone:** Phase 1

### KOS-004 — Kernel package scaffold
- **Purpose:** Establish `kernel/` as the formal coordination namespace per v0.2 §0's kernel definition.
- **Background:** Currently `router.py` lives at `tools/router.py`; v0.2 requires the kernel be a named, bounded surface.
- **Files involved:** `tools/router.py`
- **New files:** `kernel/__init__.py`, `kernel/router.py` (relocated content)
- **Existing files to modify:** `tools/router.py` → becomes a shim: `from kernel.router import *`
- **Implementation requirements:** Move dispatch logic verbatim, no behavior changes in this PR. Update internal imports across agents to reference `kernel.router` going forward (can be gradual — shim keeps old imports working).
- **Acceptance criteria:** All existing tests for router dispatch pass unchanged; no agent breaks; shim confirmed working.
- **Definition of Done:** Merged, CI green, shim verified.
- **Dependencies:** none
- **Estimated complexity:** S
- **Suggested labels:** `kernel`, `refactor`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-005 — LLMPort interface + multi_api.py adapter
- **Purpose:** Wrap the existing 8-API fallback chain behind a stable interface so providers become swappable adapters.
- **Files involved:** `multi_api.py` (read-only reference)
- **New files:** `ports/llm_port.py`, `adapters/llm/multi_api_adapter.py`
- **Existing files to modify:** callers of `multi_api.py` — update to call through `LLMPort`, one call site at a time, not in bulk in this PR.
- **Implementation requirements:** `LLMPort` as a `Protocol`/ABC with a minimal method set (e.g. `complete(prompt, **kwargs) -> str`). Adapter must not change fallback chain behavior — it's a wrapper, not a rewrite.
- **Acceptance criteria:** Adapter passes through to `multi_api.py` unchanged; existing fallback behavior verified identical via existing tests or manual check.
- **Definition of Done:** Merged, at least one real call site migrated to prove the interface works end-to-end.
- **Dependencies:** KOS-004 (kernel scaffold should exist first, though not a hard blocker)
- **Estimated complexity:** M
- **Suggested labels:** `ports-adapters`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-006 — MemoryPort interface + store.py (RAG) adapter
- **Purpose:** Same pattern as KOS-005, applied to the RAG store.
- **New files:** `ports/memory_port.py`, `adapters/memory/rag_store_adapter.py`
- **Existing files to modify:** callers of `store.py`, migrated incrementally.
- **Implementation requirements:** Interface covers at minimum `query(...)` and `upsert(...)`. No change to underlying vector store or chunking behavior in this PR — that's KOS-002's documented decision, not something to touch here.
- **Acceptance criteria:** RAG queries return identical results pre/post adapter for a fixed test set.
- **Definition of Done:** Merged, one real call site migrated.
- **Dependencies:** KOS-004
- **Estimated complexity:** M
- **Suggested labels:** `ports-adapters`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-007 — ToolPort interface + router.py dispatch adapter
- **Purpose:** Wrap kernel dispatch itself behind a Port, per v0.2 §0/§2.
- **New files:** `ports/tool_port.py`, `adapters/tools/router_adapter.py`
- **Existing files to modify:** none required immediately — this can sit alongside `kernel/router.py` without forcing callers to migrate yet.
- **Implementation requirements:** Interface exposes `dispatch(intent, payload) -> result`, delegating to `kernel/router.py`.
- **Acceptance criteria:** Adapter dispatch output identical to calling `kernel/router.py` directly.
- **Definition of Done:** Merged.
- **Dependencies:** KOS-004
- **Estimated complexity:** S
- **Suggested labels:** `ports-adapters`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-008 — Decision log schema (event sourcing store)
- **Purpose:** Create the append-only local log that scope_gate and verify_* will write to.
- **New files:** `kernel/decision_log.py`, migration/schema file (e.g. `kernel/decision_log_schema.sql`)
- **Implementation requirements:** SQLite, append-only (no UPDATE/DELETE exposed in the API), schema minimum: `id, timestamp, actor, decision_type, input_summary, outcome, reason`. Must be safe to call from a subprocess (Code Agent, once isolated) without lock contention — use WAL mode.
- **Acceptance criteria:** Concurrent writes from two processes don't corrupt the log (basic concurrency test).
- **Definition of Done:** Merged, unit tests for write/read, no update/delete path exists.
- **Dependencies:** none (can run parallel to Ports work)
- **Estimated complexity:** M
- **Suggested labels:** `event-sourcing`, `storage`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-009 — Wire scope_gate confirmations into decision log
- **Purpose:** Every scope_gate arm/disarm/allow/deny event becomes a durable log entry.
- **Files involved:** `security/scope_gate.py` (path to confirm)
- **Existing files to modify:** `scope_gate.py` — add `decision_log.record(...)` calls at each decision point.
- **Implementation requirements:** Log every gate decision, not just denials — the Reflection Agent needs full history, not just failures.
- **Acceptance criteria:** Manual test: trigger an offensive-tool request, confirm a log row appears with correct outcome.
- **Definition of Done:** Merged, verified against ADR-003 (KOS-003) description.
- **Dependencies:** KOS-008
- **Estimated complexity:** S
- **Suggested labels:** `event-sourcing`, `security`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-010 — Wire verify_identity / verify_business into decision log
- **Purpose:** Give JOTHAM client-facing verification calls an audit trail.
- **Files involved:** `verify_identity` / `verify_business` modules (path to confirm — not in prior scans)
- **Implementation requirements:** Same pattern as KOS-009. Confirm whether verification inputs contain client PII before logging — if so, log a reference/hash rather than raw input.
- **Acceptance criteria:** Log entries exist for verification calls without storing raw PII in plaintext.
- **Definition of Done:** Merged, PII handling explicitly reviewed.
- **Dependencies:** KOS-008
- **Estimated complexity:** S–M (depends on whether PII redaction logic already exists)
- **Suggested labels:** `event-sourcing`, `security`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-011 — Watchdog for run_daemon.py
- **Purpose:** Restart the daemon on crash; first concrete "self-healing" behavior.
- **New files:** `kernel/watchdog.py`
- **Existing files to modify:** `run_daemon.py` (or its launcher script) to run under the watchdog.
- **Implementation requirements:** Restart on nonzero exit, backoff on repeated crashes, log restarts to `decision_log` (crash is a decision-relevant event). Default to disarmed/safe state on restart, per ADR-003's fail-closed principle.
- **Acceptance criteria:** Kill the daemon process manually, confirm watchdog restarts it and logs the event.
- **Definition of Done:** Merged, manual crash test passed.
- **Dependencies:** KOS-004, KOS-008
- **Estimated complexity:** M
- **Suggested labels:** `kernel`, `runtime`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-012 — Code Agent subprocess isolation + IPC
- **Purpose:** Move Code Agent execution into its own subprocess so a crash there can't take the whole assistant down.
- **New files:** `agents/code/subprocess_runner.py`, `runtime/ipc.py`
- **Existing files to modify:** Code Agent's current entrypoint — becomes a thin caller into the subprocess.
- **Implementation requirements:** stdin/stdout JSON protocol or local socket, whichever is simpler given Termux constraints (prefer stdin/stdout — fewer moving parts on constrained hardware). Kernel watchdog (KOS-011) supervises this subprocess specifically, not just the top-level daemon.
- **Acceptance criteria:** A crash inside Code Agent execution (e.g. malformed generated code) does not crash the parent process; kernel/watchdog detects and restarts only the Code Agent subprocess.
- **Definition of Done:** Merged, crash-isolation test passed, `decision_log` records the crash+restart.
- **Dependencies:** KOS-011
- **Estimated complexity:** L (highest-complexity Phase 1 item — most likely candidate to split further if it grows)
- **Suggested labels:** `kernel`, `runtime`, `security`, `phase-1`
- **Suggested milestone:** Phase 1

### KOS-013 — LGU/audit-grade scope decision (governance, non-code)
- **Purpose:** Resolve v0.2 §5's open question before it silently gets decided by default.
- **Files involved:** none — this is a decision record, not code.
- **New files:** `docs/decisions/scope-lgu-vs-general.md` (or fold into an ADR if the answer is "yes, adopt")
- **Implementation requirements:** Kerr decides: general-purpose for JOTHAM clients, or scoped toward LGU/government audit deployment. Record the decision and its rationale.
- **Acceptance criteria:** A written decision exists.
- **Definition of Done:** Decision recorded; if "LGU-scoped," file follow-up issues for MemoryPort/ToolPort audit-immutability extensions (Phase 2, not now).
- **Dependencies:** none — does not block any Phase 1 code work
- **Estimated complexity:** XS (decision, not implementation)
- **Suggested labels:** `governance`, `decision-needed`
- **Suggested milestone:** Phase 1 (decide before Phase 2 planning starts)

---

## 6. Architecture Validation

| Principle | Status across this backlog |
|---|---|
| Thin Kernel | Preserved — kernel package (KOS-004) contains only dispatch, watchdog, decision log. No business logic added to `kernel/`. |
| Ports & Adapters | Preserved — KOS-005/006/007 wrap, don't rewrite, existing systems. |
| Userspace Agents | Preserved — no issue gives an agent control-flow authority over another agent or over the kernel. |
| No Vendor Lock-in | Preserved — LLMPort abstraction (KOS-005) is exactly the mechanism that keeps this true. |
| Event Sourcing | Preserved and scoped correctly — KOS-008/009/010 only touch scope_gate and verify_*, not RAG or chat state, matching v0.2 §4. |
| Human Approval | Preserved — KOS-013 is explicitly a human decision, not automated; ADRs (KOS-001-003) are marked for Kerr's review. |
| Milestone-driven evolution | **This is the principle most at risk from the request itself.** Fully decomposing Phase 2/3 into GitHub issues now — before their triggers fire — would violate this principle by front-loading speculative work. This backlog deliberately stops at placeholder-level for Phase 2/3 (§4 above) rather than producing detailed issues for them. |

**No violations found in the Phase 1 backlog as specified.**

---

## 7. Implementation Order (sequenced)

1. KOS-001, KOS-002, KOS-003 (ADRs — no dependencies, fast, do first)
2. KOS-004 (kernel scaffold)
3. KOS-005, KOS-006, KOS-007 (Ports — parallelizable once KOS-004 lands)
4. KOS-008 (decision log — parallelizable with step 3)
5. KOS-009, KOS-010 (wire decision log — depends on KOS-008)
6. KOS-011 (watchdog — depends on KOS-004, KOS-008)
7. KOS-012 (Code Agent isolation — depends on KOS-011; highest complexity, do last)
8. KOS-013 (LGU decision — no code dependency, but resolve before any Phase 2 planning begins)

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `scope_gate.py`/`store.py`/`multi_api.py` paths assumed incorrectly | Medium | Low (caught immediately on first read) | Each issue requires a path-confirmation step before edits |
| KOS-012 (subprocess isolation) scope creep on constrained hardware (3.7GB RAM) | Medium | Medium | Keep IPC to stdin/stdout, avoid a socket server; test on-device early, not just in planning |
| Decision log write contention between kernel and Code Agent subprocess | Low–Medium | Medium | WAL mode specified in KOS-008; add concurrency test before merging |
| PII in verify_identity/verify_business logging | Medium | High (client trust, possible compliance exposure) | KOS-010 explicitly requires reviewing PII handling before logging raw input |
| Watchdog restart loop masking a real crash-causing bug | Low | Medium | Backoff + cap restart attempts, log every restart to decision_log for later Reflection Agent review |
| KOS-013 left undecided indefinitely | Medium | Low now, higher at Phase 2 | Milestone gate explicitly ties it to "before Phase 2 planning starts" |

---

## 9. Testing Strategy

- **Unit level:** each Port interface tested against a mock adapter before the real adapter is wired in (KOS-005/006/007).
- **Integration level:** decision log read/write and concurrency (KOS-008) tested before scope_gate/verify_* wiring (KOS-009/010) depends on it.
- **Crash/chaos testing:** manual kill tests for both the daemon watchdog (KOS-011) and Code Agent subprocess isolation (KOS-012) — this is the actual acceptance criteria for "self-healing," not just code review.
- **Regression:** every adapter PR (KOS-005/006/007) must show pre/post behavior parity against the system it wraps — the whole point of Ports & Adapters is zero behavior change during the wrap.
- **No test infrastructure changes proposed** — reuse whatever test runner already exists in the repo; this backlog assumes it, doesn't replace it.

---

## 10. Documentation Plan

- ADRs (KOS-001/002/003) are the primary documentation deliverable for Phase 1 — no separate docs tree per v0.2 §3's explicit rejection of a 10-tier `/docs` structure.
- `docs/decisions/` holds non-ADR governance decisions like KOS-013.
- No README/wiki work is in this backlog — that was already flagged separately as a pre-existing gap (stub README, public repo) and is a documentation-hygiene task independent of this architecture rollout.
- Each new Port/adapter file should carry a module-level docstring stating what it wraps and what it deliberately does *not* change — this is cheaper than separate docs and keeps the "thin kernel, dumb adapters" intent visible in the code itself.
