
Educational Purpose

This project is intended solely for educational, research, and software engineering purposes. It exists to explore AI operating system architecture, systems design, automation, and related technologies in a controlled and ethical manner. It is not intended to facilitate unauthorized, harmful, or illegal activities.

«Warning: Users are responsible for complying with all applicable laws, regulations, and organizational policies. Any misuse of this project is the sole responsibility of the user. The authors and contributors assume no liability for improper or unauthorized use.»


KerrOS

«A modular AI Operating System (AIOS) built around a deterministic kernel, capability-driven architecture, and local-first intelligence.»

---

Vision

KerrOS is an AI Operating System designed to manage intelligent components as operating-system resources rather than isolated application features.

Instead of embedding orchestration logic into individual agents or tools, KerrOS provides a central kernel responsible for lifecycle management, capability discovery, dependency injection, scheduling, security, and state management.

The objective is to create an extensible platform where agents, tools, workflows, providers, models, and knowledge systems can evolve independently while remaining governed by a stable architectural foundation.

---

Why KerrOS?

Modern AI systems often accumulate tightly coupled components:

- Agents instantiate tools directly.
- Providers are hardcoded.
- Routing logic becomes increasingly complex.
- Documentation diverges from implementation.
- Features grow faster than architecture.

KerrOS addresses these problems by treating AI capabilities as managed system resources governed by a kernel rather than application logic.

The project prioritizes long-term maintainability over short-term feature velocity.

---

Design Goals

KerrOS is designed to provide:

- Deterministic architecture
- Stable kernel interfaces
- Capability discovery
- Modular services
- Local-first deployment
- Multi-provider AI support
- Knowledge management
- Long-term memory
- Event-driven orchestration
- Production-grade engineering

---

Core Principles

Every architectural decision should reinforce these principles.

Principle| Description
Kernel First| The kernel owns lifecycle, orchestration, permissions, and system state.
Capability Driven| Every component is a registered capability with explicit metadata.
Single Source of Truth| Machine-readable manifests generate documentation and discovery.
Loose Coupling| Components communicate through services and events rather than direct dependencies.
High Cohesion| Every module has one well-defined responsibility.
Deterministic Behavior| Configuration and metadata drive behavior instead of implicit logic.
Least Privilege| Components receive only the permissions they require.
Documentation as Code| Documentation is generated from structured metadata whenever possible.

---

High-Level Architecture

                   User Interfaces
          CLI • API • Web • Automation
                    │
                    ▼
               KerrOS Kernel
                    │
    ┌───────────────┼────────────────┐
    │               │                │
    ▼               ▼                ▼
Registry      Service Manager    Event Bus
    │               │                │
    ├───────┬───────┴────────┬───────┤
    ▼       ▼                ▼       ▼
 Agents   Tools         Workflows  Providers
    │
    ▼
Knowledge • Memory • Models • Storage

The kernel is the only component responsible for coordinating system resources.

Everything else is managed through explicit interfaces.

---

System Components

Kernel

The kernel provides:

- Boot sequence
- Lifecycle management
- Dependency injection
- Configuration
- Scheduling
- State management
- Security enforcement
- Service orchestration

---

Capability Registry

The registry is the authoritative source for every system capability.

It describes:

- Agents
- Tools
- Providers
- Models
- Workflows
- Services
- Policies
- Permissions

---

Service Manager

Responsible for:

- Startup
- Shutdown
- Restart
- Health monitoring
- Dependency ordering
- Recovery

---

Event Bus

Provides asynchronous communication between system components through typed events.

This minimizes coupling while improving extensibility and observability.

---

Knowledge System

Supports structured and unstructured knowledge sources including documentation, datasets, security references, and retrieval pipelines.

---

Memory System

Supports:

- Working memory
- Conversation memory
- Long-term memory
- Semantic memory
- Persistent storage

---

Repository Structure

core/           Kernel and runtime
agents/         Autonomous agents
tools/          System capabilities
providers/      AI model providers
registry/       Capability manifests
knowledge/      Knowledge services
memory/         Memory subsystem
workflows/      Execution workflows
services/       Runtime services
skills/         Human documentation
docs/           Architecture and ADRs
tests/          Automated tests
scripts/        Build and maintenance tools

---

Project Status

KerrOS is currently in its foundational architecture phase.

Phase| Status
Kernel Contract| In Design
Capability Registry| Planned
Service Manager| Planned
Event Bus| Planned
Permission System| Planned
Storage Architecture| Planned
Runtime Self-Healing| Planned

Expect architectural changes while the kernel foundation is established.

---

Roadmap

P0 — Kernel Foundation

- Kernel contract
- Boot lifecycle
- Dependency injection
- Configuration system

P1 — Capability Registry

- Registry schema
- Validation
- Discovery
- Manifest generation

P2 — Runtime

- "kerrd"
- Service manager
- IPC
- Health monitoring

P3 — Event Infrastructure

- Event bus
- Scheduler
- Workflow execution

P4 — Security

- Capability permissions
- Policy engine
- Access control

P5 — Storage

- Memory hierarchy
- Vector indexing
- Knowledge vault
- Persistent storage

P6 — Autonomous Runtime

- Self-healing
- Monitoring
- Telemetry
- Recovery

---

Engineering Standards

KerrOS follows a system-engineering approach.

Every contribution should preserve:

- Stable interfaces
- Deterministic architecture
- Clear module boundaries
- Loose coupling
- High cohesion
- Backward-compatible kernel evolution
- Architecture Decision Records (ADRs) for significant design changes

---

Documentation

The repository separates concerns:

- README.md — Project overview
- ARCHITECTURE.md — System architecture
- ROADMAP.md — Development milestones
- CONTRIBUTING.md — Contribution workflow
- SECURITY.md — Security model
- docs/adr/ — Architecture Decision Records

Documentation should evolve alongside implementation and, where practical, be generated from registry metadata.

---

Contributing

Contributors are encouraged to understand the architectural principles before implementing new features.

Major design changes should be documented through an Architecture Decision Record (ADR) and align with the kernel-first architecture.

---

License

License information will be added as the project approaches its first stable release.

---

«Current Status: KerrOS is an experimental AI Operating System under active architectural development. Interfaces, schemas, and internal components may change until the kernel contract reaches stability.»

## Grounded facts (verified just now)

**OmniRoute** — real project, MIT-licensed, on GitHub (canonical repo: `diegosouzapw/OmniRoute`, several forks exist since it's open-source). Current release `v3.8.49`. Key facts, not assumptions:

- **Stack: 100% TypeScript / Node.js**, not Python. Deployed as npm global install, Docker (multi-arch AMD64+ARM64), Electron desktop, or Termux (Android, no root). This is the single most important integration fact — it does **not** share a runtime with KerrOS.
- **What it is architecturally**: an OpenAI-compatible HTTP gateway (`/v1/chat/completions` etc.) that sits in front of ~290 LLM providers, with a "combo" abstraction — chains of models routed via 19 strategies (priority, cost-optimized, headroom, fusion, pipeline, etc.), 4-tier fallback cascade (Subscription → API key → Cheap → Free).
- **Resilience**: 3 independent layers — provider-level circuit breaker, per-key connection cooldown, per-model lockout. This is a more mature version of what KerrOS's `multi_api.py` fallback chain does manually.
- **Compression**: a 12-engine stacked pipeline (RTK, Caveman, LLMLingua-2/MobileBERT ONNX, etc.) claiming ~78–95% token savings on tool-heavy sessions, code/JSON always preserved byte-exact.
- **Security surface** (this matters for your "find vulnerabilities" goal): AES-256-GCM encrypted key storage, prompt-injection guardrails with a red-team eval suite, PII redaction, loopback-only process-spawning routes, and — notably — a **transparent MITM/TPROXY decrypt feature** (per-SNI CA + trust-store installer) for capturing CLI traffic that ignores proxy env vars. That's a legitimate debugging feature but also the kind of component you'd want to audit hardest if you ever expose OmniRoute beyond localhost, since a local MITM CA is a high-value target if compromised.
- **Extensibility**: exposes itself as an MCP server (104 tools, 3 transports, 31 scopes) and an A2A JSON-RPC agent — meaning other agents (including KerrOS) can drive OmniRoute programmatically, not just call it as an LLM endpoint.
- **Persistence**: SQLite (`better-sqlite3`, with pure-JS/WASM fallback) for local audit trail, memory (FTS5 + vector), usage/cost logs.

Source: [github.com/diegosouzapw/OmniRoute](https://github.com/diegosouzapw/OmniRoute) (README, `docs/` tree, ⭐26.6k, 500+ contributors, forked from `9router` + a TS port of Go's `CLIProxyAPI`).

## KerrOS architecture (from what you've already built)

Python/Termux, Hexagonal Ports & Adapters (`LLMPort` → `multi_api.py`, `MemoryPort` → RAG store, `ToolPort` → `router.py`), 238K-chunk RAG, ReactAgent ecosystem, scope-gated tool dispatch, event-sourced audit log for offensive tools — this is architecturally *compatible* with OmniRoute in spirit (both converged independently on gateway/adapter + fallback-chain + audit-log patterns) but built in a different language on a different device class.

## Integration analysis — where the seam actually is

The clean integration point is your **`LLMPort`**, not a rewrite. `LLMPort` already abstracts "how KerrOS talks to models" away from the rest of the kernel. Today it wraps `multi_api.py` (Groq, NVIDIA NIM, 8-API fallback). OmniRoute's OpenAI-compatible endpoint can become **one more adapter behind that same port** — or eventually *replace* `multi_api.py`'s fallback logic entirely, since OmniRoute's routing/circuit-breaker/compression stack is strictly more capable than a hand-rolled fallback chain.

Two integration modes, not mutually exclusive:
1. **KerrOS as OmniRoute client** — phone-side KerrOS (Termux, RAM-constrained) sends chat completions to a server-hosted OmniRoute at `http://<droplet-ip>:20128/v1`, using your existing `LLMPort` interface, just pointed at a new base URL/adapter instead of direct provider APIs.
2. **KerrOS as OmniRoute-driven agent** — since OmniRoute exposes MCP/A2A, a KerrOS agent (e.g. your Research or Planner agent) can call OmniRoute's own management tools (combo switching, cost checks, provider health) as *tools*, not just as an inference backend. This turns OmniRoute into infrastructure KerrOS actively manages, not just calls.

This also directly resolves your stated long-term infra goal — moving off phone-RAM constraints onto a rented server while staying zero-cost — since OmniRoute's whole reason to exist is squeezing free/cheap tiers with fallback, which is exactly your Phase 2/3 gating logic already.

## Roadmap: foundation → full stack

**Phase 0 — Foundation (now, no cost)**
- Re-provision the DigitalOcean droplet (Docker + Ubuntu 24.04) you'd already decided on but paused.
- Deploy OmniRoute via Docker (`docker run … diegosouzapw/omniroute`), bind to `127.0.0.1` initially, front it with a reverse proxy (Caddy, per their own guide) once you need remote access — don't expose the raw port publicly given the MITM/admin surface.
- Connect 2–3 free providers first (Kiro, OpenCode Free, Pollinations) to validate `auto` routing works before touching KerrOS at all.

**Phase 1 — Adapter integration**
- Add a new adapter under `LLMPort` (e.g. `omniroute_adapter.py`) implementing the same interface `multi_api.py` does, pointed at your droplet's `/v1`.
- Keep `multi_api.py` as a local fallback-of-last-resort (offline mode still needs to work without the droplet).
- Write the ADR for this decision — it's exactly the kind of expensive-to-reverse call your ADR process is meant for (do you route through OmniRoute always, or only online-mode?).

**Phase 2 — Fallback consolidation (trigger: first paying use of the server, per your existing gating)**
- Let OmniRoute's 4-tier cascade and circuit breakers subsume what `multi_api.py`'s dead-API caching/retry logic does today — reduces code you maintain.
- Wire OmniRoute's cost/usage headers (`X-OmniRoute-*`) into KerrOS's existing event-sourced audit log so LLM spend joins your scope_gate decision log as one audit trail.

**Phase 3 — Agent-level control (trigger: JOTHAM revenue funds a GPU, per your existing roadmap)**
- Give a KerrOS agent MCP access to OmniRoute itself (`claude mcp add-server omniroute --type http --url .../api/mcp/stream` pattern, but from KerrOS's own agent framework) so Planner/Reflection agents can adjust combos, check quota, or swap routing strategy autonomously instead of you doing it by hand.
- At this point OmniRoute effectively becomes KerrOS's remote inference organ, managed the same way `scope_gate.py` manages tool dispatch.

**Security hardening (parallel track, since you flagged vulnerability-finding as a goal)**
- Audit the MITM/TPROXY feature specifically before ever binding OmniRoute beyond loopback — a locally-trusted CA is the highest-value target in that stack.
- Verify `AGE-256-GCM`-at-rest key storage config matches your threat model (Termux/Android already has weaker at-rest guarantees than a hardened server).
- Run their own `promptfoo`/red-team eval suite for prompt-injection guardrails against your own RAG-injected prompts, since KerrOS auto-injects RAG context every turn — a gap in *your* injection surface won't be caught by *their* eval unless you add your own cases.
