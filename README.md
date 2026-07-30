# KerrOS × OmniRoute — Single Source of Truth
Architecture & Build Roadmap — v0.1, July 25, 2026

## Product scope (locked)

KerrOS is an **open-source local AI router/proxy gateway**.  
It is not a governance platform. Its target outcomes are:
- persistent conversational memory (deterministic keyword + vector recall),
- one unified local endpoint for provider routing,
- per-tool setup abstraction through kernel-managed capabilities,
- self-extensible workflows/skills/tools with auditable guardrails.

## 0. Provenance — public vs. private

| 🌐 Public (independently verifiable) | 🔒 Private (your project state only) |
|---|---|
| OmniRoute architecture, features, security model — github.com/diegosouzapw/OmniRoute, release v3.8.49, MIT, ⭐26.6k | KerrOS's target AIOS/kernel architecture — from your uploaded README.md |
| | KerrOS's actual current build state (RAG, agents, scope_gate, DevOps pipeline) — from prior session notes, not yet reflected in the public README |

Left column is checkable against the repo. Right column is accurate only as far as your own build log is — this doc doesn't independently verify KerrOS's code, it reconciles two different framings of the same project that you've given me at different times.

## 1. The one decision to make before P0

Your README describes a **general-purpose kernel**: it owns lifecycle management, capability discovery, dependency injection, scheduling, security enforcement, state management, and service orchestration — plus a separate Capability Registry, Service Manager, Event Bus, and Policy Engine.

That's materially bigger than the kernel you already ADR'd. That decision — logged as resolved — explicitly **rejected** a full IPC actor-mesh orchestrator as premature, and defined "kernel" narrowly as `router.py` + 3 Ports (LLM/Memory/Tool) + a minimal watchdog + the scope_gate decision log, with agents staying in userspace and calling the kernel rather than the kernel owning them.

Two different architectures, not two names for one thing. Building toward the README's version without revisiting that ADR is exactly the undocumented drift ADRs exist to catch. Two honest paths:

- **A — Grow into it.** Keep the narrow kernel now (it's sized right for 3.7GB RAM / $0 budget). Treat P0–P6 as target-state you earn into as your existing Phase 2/3 infra triggers hit (rented server, GPU funded) — same milestone-gating you already use. Log an ADR now saying "P0–P6 is target-state, gated the same way as the existing roadmap."
- **B — Commit now.** If the README is a real decision to rebuild as a formal AIOS starting immediately, that's legitimate — but it reverses the earlier ADR's reasoning, and the reversal deserves its own ADR entry, not a silent supersede.

Everything below works under either path — only the *timing* changes. Given your zero-cost/phone-RAM constraints haven't changed, A is the more grounded default, but that's yours to log, not mine to pick.

## 2. Principle-by-principle reality check

Checked against what's actually built on `main` (July 2026):

| Principle | Status | Evidence |
|---|---|---|
| Least Privilege | ✅ Strong | `scope_gate.py` fail-closed blocking, explicit-command gating, time-limited arm/disarm on deploy tools; `shell=False` + `safe_commands` for exec |
| Loose Coupling | 🟡 Partial | Ports pattern (LLM/Memory/Tool/Storage/DB/Embedding/Search) + `kernel/access.py`; residual direct imports in batch `import_*.py` scripts |
| High Cohesion | 🟡 Likely | Single-responsibility agent split (Knowledge/Security/Code/Research/Planner/Reflection/Document) |
| Kernel First | 🟡 Partial | True for security/dispatch decisions; agents stay userspace by design (`kernel/access` facades) |
| Capability Driven | ✅ Strong | `kernel/capability_registry.py` + manifests for claw, router (scope_policy), devops, agents, multi_api providers, ports; OmniRoute stays one meta-provider |
| Single Source of Truth (docs from manifests) | ✅ Strong | `scripts/render_capabilities.py` → [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) (`--check` for drift) |
| Deterministic Behavior (config-driven) | 🟡 Partial | `kernel/config.py` + `config.json` / env; tool detection still largely code-driven |
| Documentation as Code | ✅ Strong | Capability + scope policy docs generated (`docs/CAPABILITIES.md`, `docs/SCOPE_POLICY.md`); ADRs remain hand-written |

Net: P0–P3 foundations are in place. **P1 Capability Registry covers claw, scope-gated router tools, devops, agents, multi_api providers, and ports** — regenerate docs after manifest edits.

## 3. Unified repo structure

Mapping the README's proposed layout onto what's already built, so nothing gets orphaned:

| README dir | Maps to (already built) | Notes |
|---|---|---|
| `core/` | `cli/chat.py`, `tools/router.py`, `core/context.py` | canonical active path; `agents/supervisor/` is confirmed dead code, don't migrate it |
| `agents/` | Knowledge, Security, Code, Research, Planner, Reflection, Document agents | ReactAgent pattern, from scratch |
| `tools/` | `tools/router.py` dispatch, `tools/scope_gate.py`, `tools/code_saver.py`, 8 DevOps tools | |
| `providers/` | `multi_api.py` (Groq primary, NVIDIA NIM, 8-API fallback) | **OmniRoute becomes a new entry here** — §5, P1 |
| `registry/` | `kernel/capability_registry.py`, `config/capabilities/` | P1 — manifests + generated [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) |
| `knowledge/` | RAG store: 238K chunks, 13 categories (NIST/CWE/CVE/Sigma/YARA/CISA KEV) | |
| `memory/` | `runtime/daily_learning.py`, episodic→semantic consolidation, hybrid memory adapter | |
| `workflows/` | `runtime/workflows.py` DAG engine + YAML defs | P3; [`ADR-010`](docs/adr/ADR-010-workflow-yaml.md) |
| `services/` | `kerrd`, `runtime/services.py`, `kernel/watchdog.py` | |
| `skills/` | progressive-disclosure skills (ADR-007) | |
| `docs/`, `docs/adr/` | ADR-001..007 (Accepted) + PHASE2/PHASE3 docs | |

## 4. OmniRoute — verified, condensed (🌐)

- Node.js/TypeScript, MIT license, self-hosted, OpenAI-compatible `/v1` endpoint, default port `20128`
- 290 providers, 90+ free tiers (40+ free forever), 19 routing strategies, 4-tier fallback (Subscription → API key → Cheap → Free)
- 3-layer resilience: provider circuit breaker, per-key cooldown, per-model lockout
- 12-engine compression stack (RTK, Caveman, LLMLingua-2, etc.), ~78–95% token savings on tool-heavy sessions, code/JSON always byte-preserved
- MCP server (104 tools, 31 scopes) + A2A JSON-RPC agent protocol — externally controllable, not just callable
- Security: AES-256-GCM key encryption at rest, prompt-injection guard with a red-team eval suite, opt-in PII redaction, loopback-only process routes, and a **MITM/TPROXY decrypt feature with a locally-trusted CA** — flagged as the top audit item in §6
- Deploys via Docker (AMD64+ARM64), npm, Electron, or Termux itself

## 5. Roadmap: P0 → P6

### P0 — Kernel Foundation
**Status: done (foundation).**
- [x] Kernel contract, boot lifecycle, DI — `kernel/contract.py`, `boot.py`, `container.py` (ADR-004)
- [x] Config module — `kernel/config.py` (+ `core/config.py` legacy)
- [x] Decision log + scope_gate / verify_* audit wiring (KOS-008..010)
- [x] Watchdog + Code Agent subprocess IPC (KOS-011, KOS-012)

### P1 — Capability Registry
**Status: foundation complete (expanded coverage).**
- [x] Minimal manifest schema + registry — `kernel/capability_registry.py`, `config/capabilities/`
- [x] Boot registers `capability_registry` and bootstraps claw tool definitions
- [x] Manifests for claw FS tools, scope_policy router tools, agents, DevOps (+ extras), multi_api providers, ports
- [x] OmniRoute touchpoint: register it as **one** capability entry (a meta-provider), not 290 — let OmniRoute's own dashboard stay the source of truth for its provider catalog
- [x] Generate docs/status from manifests (Documentation as Code) — `scripts/render_capabilities.py` → [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md)
- [x] Parity tests — claw / `scope_policy` / multi_api keys ↔ manifests (`tests/unit_kernel/test_capability_manifest_parity.py`)

### P2 — Runtime (`kerrd`, service manager, IPC, health)
**Status: foundation implemented** (`docs/PHASE2.md`, ADR-005).
- [x] `kerrd` + `ServiceManager` + `HealthMonitor` + in-process service bus
- [x] Code Agent IPC worker (`runtime/ipc.py`, `agents/code/subprocess_runner.py`)
- [x] IPC actor-mesh foundation (nng/socket) — `runtime/actor_mesh.py` ([`ADR-012`](docs/adr/ADR-012-actor-mesh.md)); optional `pynng`
- [x] Actor orchestrator foundation — named routes, req/reply, `add_peer`, WAN token gate ([`ADR-018`](docs/adr/ADR-018-actor-mesh-orchestrator-foundation.md))
- [x] Actor supervision foundation — local heartbeats, TTL liveness, `_sys.ping` ([`ADR-020`](docs/adr/ADR-020-actor-mesh-supervision-foundation.md))
- [x] Actor mesh mTLS + NATS + remote restart foundation — stdlib TLS, soft nats-py, ServiceManager hook ([`ADR-023`](docs/adr/ADR-023-actor-mesh-mtls-nats-remote.md))
- [x] JetStream soft + OTP tree + CA reload foundation — durable pub stub, local one-for-one tree, PEM mtime reload ([`ADR-028`](docs/adr/ADR-028-actor-mesh-jetstream-otp-ca.md))
- [x] JetStream cluster failover + ACME watch — multi-URL client HA + live-dir TLS reload ([`ADR-029`](docs/adr/ADR-029-jetstream-cluster-acme.md))
- [x] Supercluster topology + ACME HTTP-01 — registry/validate + stdlib challenge solver ([`ADR-030`](docs/adr/ADR-030-supercluster-http01.md))
- [x] Supercluster ops + ACME account/DNS-01 — plan/probe/apply + local account + memory DNS-01 ([`ADR-031`](docs/adr/ADR-031-supercluster-ops-dns01.md))
- [x] Supercluster control-plane + ACME newAccount/cloud DNS — config publish/monitor + fake/webhook DNS ([`ADR-032`](docs/adr/ADR-032-control-plane-acme-live.md))
- [x] Broker lifecycle + ACME JOSE + cloud DNS SDK facades — memory/subprocess broker, JWS/order, Route53/CF soft ([`ADR-033`](docs/adr/ADR-033-broker-jose-dns-sdk.md))
- [x] Hardware WORM + crypto-shred + IdP portals — appliance mirror, DEK shred, data-subject portal ([`ADR-034`](docs/adr/ADR-034-hardware-worm-cryptoshred-idp.md))
- [x] Multi-broker fleets + ACME issuance — fleet manager + fake challenge→cert pipeline ([`ADR-035`](docs/adr/ADR-035-broker-fleet-acme-issuance.md))
- [x] SoA draft + OIDC RP — ISO SoA foundation + authorization-code RP ([`ADR-036`](docs/adr/ADR-036-soa-oidc-rp.md))
- [x] Remote fleet orchestration + packaged production ACME — fake/HTTP/SSH agents + certbot/acme.sh soft ([`ADR-037`](docs/adr/ADR-037-remote-fleet-prod-acme.md))
- [x] Fleet inventory + K8s operator + ACME renewal timers — CMDB-lite, Fake/kubectl operator, tickable renew ([`ADR-038`](docs/adr/ADR-038-inventory-k8s-renewal.md))
- [x] Docker event mesh kit — `deploy/event_mesh/` two-node HTTP compose ([`ADR-011`](docs/adr/ADR-011-docker-event-mesh.md))
- [x] LGU audit immutability foundation — decision_log hash chain + JSONL export + port hooks ([`ADR-017`](docs/adr/ADR-017-decision-log-tamper-evidence-export.md))
- [x] LGU software-WORM + retention — sealed JSONL segments + `audit_retention` ([`ADR-019`](docs/adr/ADR-019-decision-log-worm-retention.md))
- [x] LGU audit RBAC + SIEM forwarder — token roles + webhook/syslog ([`ADR-021`](docs/adr/ADR-021-decision-log-rbac-siem.md))
- [x] LGU Object Lock soft + ISO audit map — local/S3 mirror + control map ([`ADR-022`](docs/adr/ADR-022-decision-log-object-lock-iso-map.md))
- [x] Jurisdiction privacy foundation — egress hash/redact + GDPR/DPDP map ([`ADR-024`](docs/adr/ADR-024-jurisdiction-privacy-foundation.md))
- [x] Residency stamp + erasure request ledger — egress region + side ledger, never rewrite WORM ([`ADR-025`](docs/adr/ADR-025-residency-erasure-ledger.md))
- [x] Sealed-cold erasure review + transfer ledger — review outcomes + SCC/adequacy intents ([`ADR-026`](docs/adr/ADR-026-sealed-cold-erasure-transfers.md))
- [x] Automated transfer pipeline — local_copy / http_put execute for ledger intents ([`ADR-027`](docs/adr/ADR-027-automated-transfer-pipeline.md)); hardware WORM / crypto-shred / IdP portals foundation in [`ADR-034`](docs/adr/ADR-034-hardware-worm-cryptoshred-idp.md)
- [x] OmniRoute touchpoint: health-check the droplet's `/v1` like any managed service (`HealthMonitor` / `/health` / `kerrd health`)

### P3 — Event Infrastructure
**Status: foundation implemented** (`docs/PHASE3.md`, ADR-006).
- [x] General-purpose `EventBus` (separate from decision-log audit trail)
- [x] Scheduler + workflow DAG engine (+ SQLite run persistence / resume)
- [x] Local LLM adapters (Ollama/vLLM) behind `LLMPort` / `CompositeLLMAdapter`
- [x] Self-hosted LLM ops (C-19) — Ollama loopback compose + health probes ([`ADR-016`](docs/adr/ADR-016-local-llm-ops.md), `deploy/ollama/`)
- [x] Persistent workflow state / resume — `runtime/workflow_store.py` → `data/workflows/runs.db`
- [x] Cron expressions — `Scheduler.schedule_cron` / `runtime/cron.py` (5-field)
- [x] Workflow YAML definitions — `runtime/workflow_yaml.py` / `config/workflows/` ([`ADR-010`](docs/adr/ADR-010-workflow-yaml.md))
- [x] YAML tool/LLM actions — gated `tool` / `llm` builtins ([`ADR-013`](docs/adr/ADR-013-workflow-yaml-tool-llm.md))
- [x] Event mesh foundation — `LocalEventMesh` + transport Protocol ([`ADR-008`](docs/adr/ADR-008-event-mesh-foundation.md))
- [x] Event mesh transport — durable SQLite broker + peer discovery ([`ADR-009`](docs/adr/ADR-009-event-mesh-transport.md))
- [x] Docker event mesh (C-17) — HTTP ingest + Compose kit ([`ADR-011`](docs/adr/ADR-011-docker-event-mesh.md))
- [x] Authenticated mesh — shared-secret HTTP + actor envelopes ([`ADR-014`](docs/adr/ADR-014-authenticated-mesh.md))
- [x] OmniRoute touchpoint: `X-OmniRoute-*` cost/usage headers as event sources (`omniroute.usage` on EventBus)

### P4 — Security
**Status: ahead of earlier status tables.** `scope_gate.py` is a working fail-closed policy engine; shell/calc hardening landed.
- [x] Formalize rules as declarative data — `config/scope_policy.yaml` (offensive/deploy tool classes, arm defaults, messages)
- [x] Generate scope policy docs — `scripts/render_scope_policy.py` → [`docs/SCOPE_POLICY.md`](docs/SCOPE_POLICY.md)
- [x] Full audit checklist in §6 (OmniRoute bind/AES/promptfoo + DevOps tokens)
- [x] Confirm DevOps tokens are scoped least-privilege per service — [`docs/DEVOPS_TOKEN_SCOPING.md`](docs/DEVOPS_TOKEN_SCOPING.md), `tools/devops_tokens.py`

### P5 — Storage
**Status: most mature phase relative to the plan.** 238K-chunk RAG, dedup, phrase-match scoring, hybrid memory, optional Qdrant.
- [x] Lexical phrase-match scoring in `rag/store.py`; hybrid/vector path via adapters
- [x] Keep OmniRoute's own FTS5+vector memory separate from KerrOS RAG — [`docs/MEMORY_SEPARATION.md`](docs/MEMORY_SEPARATION.md) (`rag/path_guard.py`)
- [x] Optional Qdrant sidecar (C-18) — `deploy/qdrant/`, migrate script, health probe ([`ADR-015`](docs/adr/ADR-015-qdrant-optional-vector-store.md))

### P6 — Autonomous Runtime
**Status: seed started (Reflection Agent + LLM resilience).**
- [x] Reflection Agent (episode review, lesson logging) — `/reflect` → `reflections.json` + high-confidence → `semantic.lessons_learned`
- [x] OmniRoute-inspired 3-layer resilience — circuit breaker / cooldown / lockout per composite provider (`adapters/llm/resilience.py`, `/llm`)

## 6. Security audit checklist

**OmniRoute side (once integrated):**
- [x] Never bind OmniRoute beyond `127.0.0.1` without a reverse proxy — loopback compose + CI guards ([`deploy/omniroute/`](deploy/omniroute/), [`docs/OMNIROUTE_SECURITY_AUDIT.md`](docs/OMNIROUTE_SECURITY_AUDIT.md))
- [x] Verify AES-256-GCM key storage config matches threat model — `STORAGE_ENCRYPTION_KEY` / Termux vs droplet notes in audit doc + `.env.example`
- [x] Run promptfoo red-team against **KerrOS** RAG-injected prompts — fixtures + stub config ([`eval/omniroute_rag_promptfoo/`](eval/omniroute_rag_promptfoo/)); operator run via `scripts/run_omniroute_rag_promptfoo.sh`

**KerrOS side (independent of OmniRoute):**
- [x] `scope_gate.py` fail-closed default; deploy arm window expires server-side (`deploy_armed_until`)
- [x] `verify_identity`/`verify_business` log SHA-256 digests, not raw PII (KOS-010)
- [x] 8-tool DevOps pipeline (GitHub/Supabase/Vercel/Netlify/Railway/Cloudflare/Stripe) — least-privilege token checklist + shape checks ([`docs/DEVOPS_TOKEN_SCOPING.md`](docs/DEVOPS_TOKEN_SCOPING.md)); Stripe live keys refused
- [x] Shell exec uses `shell=False` + metachar rejection; `_calc` uses AST safe math (no `eval`)

## 7. Immediate next actions
1. [x] Confirm DevOps tokens are scoped least-privilege per service ([`docs/DEVOPS_TOKEN_SCOPING.md`](docs/DEVOPS_TOKEN_SCOPING.md); `python3 scripts/check_devops_tokens.py`)
2. [x] Re-provision DigitalOcean droplet + OmniRoute loopback kit — [`docs/DROPLET_RUNBOOK.md`](docs/DROPLET_RUNBOOK.md) (`scripts/omniroute_droplet.sh verify`)
3. [x] Wire OmniRoute health into `HealthMonitor` / kerrd (`components.omniroute`)
4. [x] Persist workflow state / resume; [x] cron; [x] event mesh (ADR-008/009/011/014); [x] workflow YAML + tool/LLM (ADR-010/013); [x] actor mesh (ADR-012/018)
5. [x] Complete remaining §6 OmniRoute security audit checklist items ([`docs/OMNIROUTE_SECURITY_AUDIT.md`](docs/OMNIROUTE_SECURITY_AUDIT.md))
6. [x] P3 OmniRoute touchpoint: `X-OmniRoute-*` cost/usage → `omniroute.usage` events

## 8. Open decisions log — don't resolve these silently
- Kernel scope: narrow (ADR'd) vs. full AIOS (README) — §1; default remains path A (earn into P0–P6)
- ~~Event bus: generalize the audit log vs. keep it audit-only~~ — **resolved (ADR-006):** separate `EventBus` for runtime events; decision log stays audit-only
- Vector vs. lexical RAG scoring — P5; both exist (lexical default + hybrid/Qdrant adapters)
- ~~LGU/government audit-grade vs. general-purpose scoping~~ — **resolved (KOS-013):** general-purpose scope adopted, see [`docs/decisions/scope-lgu-vs-general.md`](docs/decisions/scope-lgu-vs-general.md)
