# KerrOS × OmniRoute — Single Source of Truth
Architecture & Build Roadmap — v0.1, July 25, 2026

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

Your README's 8 Core Principles, checked against what's actually built (all 🔒, internal state):

| Principle | Status | Evidence |
|---|---|---|
| Least Privilege | ✅ Strong | `scope_gate.py` fail-closed blocking, explicit-command gating, time-limited arm/disarm on deploy tools |
| Loose Coupling | 🟡 Partial | Ports pattern (LLM/Memory/Tool) achieves this for 3 abstracted surfaces, not system-wide |
| High Cohesion | 🟡 Likely | Single-responsibility agent split (Knowledge/Security/Code/Research/Planner/Reflection/Document); unverified at code level |
| Kernel First | 🟡 Partial | True for security/dispatch decisions; explicitly *not* true for agent orchestration — agents stay userspace by design |
| Capability Driven | ❌ Gap | No formal manifest/metadata per component — `router.py` dispatch isn't a capability registry |
| Single Source of Truth (docs from manifests) | ❌ Gap | ADRs are hand-written (good), but nothing generates from structured metadata |
| Deterministic Behavior (config-driven) | ❌ Gap | No centralized config system mentioned; behavior lives in code (`detect_tool()`, explicit-command checks) |
| Documentation as Code | ❌ Gap | Same root cause — no registry to generate from |

Net: security posture and module boundaries are ahead of what the README's status table implies; the metadata/registry/config layer is behind it. That means **P1 (Capability Registry) is the actual bottleneck, not P0** — P0's substance already mostly exists.

## 3. Unified repo structure

Mapping the README's proposed layout onto what's already built, so nothing gets orphaned:

| README dir | Maps to (already built) | Notes |
|---|---|---|
| `core/` | `cli/chat.py`, `tools/router.py`, `core/context.py` | canonical active path; `agents/supervisor/` is confirmed dead code, don't migrate it |
| `agents/` | Knowledge, Security, Code, Research, Planner, Reflection, Document agents | ReactAgent pattern, from scratch |
| `tools/` | `tools/router.py` dispatch, `tools/scope_gate.py`, `tools/code_saver.py`, 8 DevOps tools | |
| `providers/` | `multi_api.py` (Groq primary, NVIDIA NIM, 8-API fallback) | **OmniRoute becomes a new entry here** — §5, P1 |
| `registry/` | — doesn't exist yet | **this is P1**, the real gap |
| `knowledge/` | RAG store: 238K chunks, 13 categories (NIST/CWE/CVE/Sigma/YARA/CISA KEV) | |
| `memory/` | `runtime/daily_learning.py`, episodic→semantic consolidation | |
| `workflows/` | implicit in agent orchestration, not formalized | overlaps P3 gap |
| `services/` | `run_daemon.py` + watchdog | |
| `skills/` | — | human-facing docs, if any |
| `docs/`, `docs/adr/` | 3 ADRs (planned/backfilled): Groq-primary fallback, 120-word/30-overlap RAG chunking, scope_gate fail-closed+arm/disarm | |

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
**Status: mostly done, under the ADR's narrower scope.**
- [x] Kernel contract exists de facto: `router.py` + 3 Ports + watchdog + scope_gate log
- [ ] Write the ADR that makes this contract explicit as your P0 deliverable — don't treat P0 as not-started
- [ ] Add a real config module (`core/config.py`) to centralize env/secrets/flags — the one genuine P0 gap

### P1 — Capability Registry
**Status: the actual bottleneck. Start here, not P0.**
- [ ] Define a minimal manifest schema (YAML/JSON): name, version, required permissions, dependencies
- [ ] Write manifests for what already exists first — 7 agents, 8 DevOps tools, LLM providers — before writing new registry code
- [ ] OmniRoute touchpoint: register it as **one** capability entry (a meta-provider), not 290 — let OmniRoute's own dashboard stay the source of truth for its provider catalog

### P2 — Runtime (`kerrd`, service manager, IPC, health)
**Status: partial.** `run_daemon.py` + watchdog exists; Code Agent → own subprocess + watchdog is already active Phase-1 work.
- [ ] Generalize the Code-Agent-subprocess pattern into a reusable service-manager primitive instead of one-off code
- [ ] OmniRoute touchpoint: once deployed, health-check the droplet's `/v1` the same way you'd health-check any managed service — the most natural integration point in the whole roadmap

### P3 — Event Infrastructure
**Status: narrow, not general.** Event sourcing exists, but scoped only to scope_gate/offensive-tool decisions + identity-verification audit trail.
- [ ] ADR: generalize the existing audit log into a real pub/sub bus, or keep it audit-only and add a separate lightweight mechanism for non-security events — don't let audit-log scope silently creep
- [ ] OmniRoute touchpoint: once this exists, its `X-OmniRoute-*` cost/usage headers become event sources; until then, log them straight into the existing scope_gate-style log

### P4 — Security
**Status: ahead of the README's own status table.** `scope_gate.py` is already a working fail-closed policy engine in substance.
- [ ] Formalize its rules as declarative data (tool → permission level → confirmation required) instead of inline logic — satisfies "Policy Engine" without a rewrite
- [ ] Full audit checklist in §6

### P5 — Storage
**Status: most mature phase relative to the plan.** 238K-chunk RAG, dedup, phrase-match scoring, episodic→semantic consolidation.
- [ ] Confirm whether `store.py` scoring is lexical (phrase-match) or true vector search — the README specifically calls for "vector indexing," worth checking this isn't overstated
- [ ] Keep OmniRoute's own FTS5+vector memory (its routing/session state) separate from your RAG — different jobs, don't merge

### P6 — Autonomous Runtime
**Status: earliest-stage, correctly sequenced last.**
- [ ] Reflection Agent (episode review, lesson logging) is your real seed here
- [ ] When you get here, imitate OmniRoute's 3-layer resilience model (circuit breaker / cooldown / lockout) rather than reinventing it — it's a working reference you already have access to

## 6. Security audit checklist

**OmniRoute side (once integrated):**
- [ ] Never bind OmniRoute beyond `127.0.0.1` without a reverse proxy in front — the dashboard and the MITM/TPROXY CA installer are the highest-value targets if this ever faces the public internet
- [ ] Verify AES-256-GCM key storage config actually matches your threat model — Termux/Android has weaker at-rest guarantees than the droplet will
- [ ] Run their `promptfoo` red-team suite against your *own* RAG-injected prompts specifically — their eval suite tests their injection surface, not yours

**KerrOS side (independent of OmniRoute):**
- [ ] `scope_gate.py`'s fail-closed default is good; confirm the arm/disarm window for `DEPLOY_TOOLS` actually expires server-side, not just client-side
- [ ] `verify_identity`/`verify_business` tools handle third-party data even if publicly-sourced — worth an explicit retention/logging policy now that the event-sourced audit trail records lookups
- [ ] 8-tool DevOps pipeline (GitHub/Supabase/Vercel/Netlify/Railway/Cloudflare/Stripe) means one compromised credential has a wide blast radius — confirm each token is scoped least-privilege, not one shared key

## 7. Immediate next actions
1. Decide A vs. B from §1, log it as an ADR
2. Write the P0 "kernel contract" ADR — documents what already exists, near-zero new work
3. Start P1 manifests for what's already built — highest-leverage gap
4. Re-provision the DigitalOcean droplet, deploy OmniRoute via Docker, bound to loopback
5. Build `omniroute_adapter.py` under `LLMPort` once the droplet is stable

## 8. Open decisions log — don't resolve these silently
- Kernel scope: narrow (ADR'd) vs. full AIOS (README) — §1
- Event bus: generalize the audit log vs. keep it audit-only — P3
- Vector vs. lexical RAG scoring — P5
- ~~LGU/government audit-grade vs. general-purpose scoping~~ — **resolved (KOS-013):** general-purpose scope adopted, see [`docs/decisions/scope-lgu-vs-general.md`](docs/decisions/scope-lgu-vs-general.md)
