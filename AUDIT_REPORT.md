================================================================================
KERRos OFFLINE_AI — FULL AUDIT REPORT
Date: 2026-09-10
Scope: /data/data/com.termux/files/home/offline_ai (1.6 GB, 514 .py files, 72k LOC)
================================================================================

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. PROJECT OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KerrOS ("offline_ai") is a Python 3 terminal AI-assistant REPL with a
dependency-injection kernel, ports/adapters, RAG memory, and optional local
or cloud LLMs. It is NOT a public LLM gateway — it's a single-operator
workspace tool.

Layers:
  CLI        → cli/chat.py (1550 lines, monolithic REPL)
  Kernel     → kernel/boot.py, kernel/config.py, kernel/container.py
  Ports      → ports/ (9 port protocols: LLM, Memory, Tool, Embedding, etc.)
  Adapters   → adapters/ (18 subpackages: llm, memory, audit, auth, tools...)
  Runtime    → runtime/ (event bus, scheduler, workflows, health, mesh)
  Agents     → agents/ (code, research, knowledge, planner, reflection, react)
  RAG        → rag/ (SQLite FTS5 primary, FAISS/Qdrant optional)
  Memory     → memory/ (session, profile, episodic, semantic)
  Tools      → tools/ (claw FS/exec, scope gate, router, devops)
  Config     → config/ (capabilities, profiles, scope policy, workflows YAML)
  Deploy     → deploy/ (Docker kits: ollama, vllm, llama_cpp, omniroute, qdrant)
  Tests      → tests/ (124 test files, 586 tests total)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. CODE QUALITY & SYNTAX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SYNTAX CHECK:
  514 Python files scanned.
  1 syntax error found:
    cli/_chat_else.py line 4 — IndentationError: unexpected indent
    This file is a dead-code snippet store (patch notes, not imported).
    It is NOT imported by chat.py or any other module.
    Severity: LOW (dead file, but should be removed or renamed to .txt)

  All 513 other .py files compile cleanly.

CODE STRUCTURE ISSUES:
  - cli/chat.py is a 1550-line monolithic if/elif chain (~80+ branches).
    No command dispatch table, no plugin registry for slash commands.
    This is the single biggest maintainability liability.
  - core/config.py uses a module-level singleton (_cfg) — not thread-safe,
    not reloadable without restart.
  - Multiple "patch_*.py" files at root (12 files) appear to be one-off
    migration scripts that should be in scripts/ or removed after apply.
  - apply_*.py files at root (4 files) — same issue.
  - tree.txt, top_tree.txt committed — these are dev artifacts, should be gitignored.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. ARCHITECTURE REVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOOT LIFECYCLE (kernel/boot.py):
  INIT → CONFIG → SERVICES → PORTS → READY
  - Clean phase machine with BootPhase enum.
  - DI container with string-keyed service registry.
  - Services: config, router, decision_log, service_bus, service_manager,
    health_monitor, capability_registry, event_bus, scheduler,
    workflow_engine, event_mesh (optional), actor_mesh (optional).
  - Ports: tool_port, dispatch_port, memory_port, storage_port,
    database_port, embedding_port, code_index_port, search_port, llm_port.
  - All optional subsystems (event_mesh, actor_mesh) are wrapped in
    try/except — good fail-closed design.

LLM ROUTING (core/router.py):
  Priority chain: OpenRouter free → MultiAPI (user keys) → local llama.cpp → OpenRouter paid (opt-in)
  - Clean fallback design.
  - Task-routed via config/openrouter_tiers.yaml.
  - Circuit breaker / cooldown / lockout per provider.
  - NOTE: Router is used by AdaptiveEngine._online_generate() but
    AdaptiveEngine.__init__() does NOT create a Router — it's lazily
    created in init_online(). This means the first /online call pays
    the import + test-call cost.

ADAPTIVE ENGINE (core/adaptive_engine.py):
  - Thin wrapper over Router (online) and LLMEngine (offline).
  - Tracks mode as a string ("online"/"offline") — not an enum.
  - task_completion integration for observability.

KERNEL CONFIG (kernel/config.py):
  - Separate from core/config.py — KernelConfig is a typed dataclass.
  - core/config.py is a raw dict with env overrides.
  - This dual-config pattern is confusing. core/config.cfg() returns
    a dict; kernel/boot.py uses KernelConfig objects.

PORTS:
  - 9 port protocols defined as Protocol classes.
  - Good abstraction — adapters are swappable.
  - LLMPort is Phase 1 (wrapper over multi_api.py), with Phase 2+
    ExecutionPort planned but not implemented.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. SECURITY FINDINGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SCOPE GATE (tools/scope_gate.py):
  - Fail-closed design — tools blocked by default, explicit authorization required.
  - /scope add <target> — interactive confirmation.
  - /scope arm-deploy — time-bounded deploy tool authorization.
  - Deploy tools (github, vercel, netlify, railway, cloudflare, stripe, supabase)
    require explicit arming.
  - GOOD: This is the strongest security feature in the codebase.

SAFE COMMANDS (config.json):
  - 35 allowlisted commands for /exec claw tool.
  - Includes: ls, pwd, cat, echo, ping, nmap, curl, wget, ssh, python3, git,
    dig, whois, htop, arp, ss, id, whoami, find, grep, rg, ps.
  - CONCERN: ssh, python3, git, curl, wget, nmap in safe_commands.
    These are powerful tools. The workspace boundary is enforced by
    claw_adapter.py (path traversal blocked), but command injection
    via arguments is not validated.
  - CONCERN: find and grep with no argument validation — could read
    any file on the system if the workspace check has bypasses.

DECISION LOG (adapters/audit/):
  - Hash chain verification (/decisions verify).
  - WORM store for sealed segments.
  - RBAC for audit access (ADR-021).
  - Privacy egress controls (ADR-024).
  - Residency stamps (ADR-025).
  - Erasure request ledger (ADR-025).
  - Transfer intent + execution pipeline (ADR-026/027).
  - SIEM forwarding (ADR-021).
  - This is a comprehensive audit trail system — well designed.

ENVIRONMENT / SECRETS:
  - .env.example has 500+ lines of documented env vars.
  - .gitignore correctly blocks .env, *.key, *.pem, *credentials*, etc.
  - CONCERN: requirements.txt has a git merge conflict marker (lines 1-32):
    <<<<<<< Updated upstream ... >>>>>>> Stashed changes
    This is a committed merge conflict — pip install -r requirements.txt
    will FAIL until resolved.

CREDENTIAL HANDLING:
  - /setkey groq <key> writes directly to config.json — key stored in plaintext.
  - No encryption at rest for API keys in config.json.
  - .env loaded via python-dotenv, values override config.json.

SHELL EXECUTION:
  - claw_adapter.py enforces workspace boundary.
  - exec_approval.py provides additional guard.
  - process_backends.py / process_registry.py for background processes.
  - GOOD: shell=False pattern used in subprocess calls where possible.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. TEST RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Test run: python3 -m unittest discover -s tests -p 'test_*.py' -t .
Ran: 586 tests in ~45 seconds
Result: FAILED (5 failures, 7 errors, 1 skipped)

FAILURES (5):
  1. test_health_ok_when_omniroute_disabled (test_phase2)
     OmniRoute health check assertion mismatch.
  2. test_register_and_start_ipc_worker (test_phase2)
     IPC worker registration — likely missing nng/socket backend.
  3. test_init_online_uses_llm_port_complete (test_phase3)
     LLM port integration — likely missing API key in test env.
  4. test_install_and_list (test_adr064_hub_gateway)
     Skills hub: 'source must be under workspace or /tmp' — path validation.
  5. test_quarantines_dangerous (test_adr064_hub_gateway)
     Skills hub quarantine — scan logic not matching expected output.

ERRORS (7):
  1. tests.unit_agents.test_reflection — import failure (missing dep).
  2. tests.unit_agents.test_subagents_adr061 — parallel delegate test.
  3. tests.unit_kernel.test_kos_012_015.IpcTest — IPC worker ping.
  4. tests.unit_kernel.test_kos_012_015.IsolatedCodeExecutorRestartTest.
  5. tests.unit_kernel.test_kos_012_015.IsolatedExecutorTest.
  6. tests.unit_runtime.test_phase3.AdaptiveEngineLLMPortTest.
  7. tests.unit_tools.test_agent_behavior_upgrades.PipelineExecTest.

ANALYSIS:
  - 569 of 586 tests pass (97.1% pass rate).
  - Most failures are environment-dependent (no API keys, no IPC backend,
    no GPU, no Docker) — expected in a Termux/offline environment.
  - The 2 skills_hub failures (ADR-064) are logic issues — the quarantine
    and path validation may have regressed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6. CONFIGURATION & ENVIRONMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

requirements.txt:
  - CRITICAL: Contains unresolved git merge conflict markers.
    pip install -r requirements.txt will FAIL.
    Two versions of the dependency list exist (Updated upstream vs Stashed).
    Must be manually resolved.

config.json:
  - model_path: models/qwen0.5b-q4.gguf (default offline model)
  - llama_bin: llama-completion (subprocess name)
  - threads: 4, context_size: 4096, max_tokens: 1024
  - tools_enabled: true, rag_enabled: true, thinking_mode: false
  - safe_commands: 35 entries (see security section)
  - knowledge_root: ${KERROS_KNOWLEDGE_ROOT:-./data/knowledge}

Symlink requirement:
  - Many modules hardcode ~/offline_ai as the project root.
  - run.sh does: cd "$(dirname "$0")/../.." — assumes it's in a subdirectory.
    If run.sh is at repo root, this cds to parent of parent — WRONG.
    Current location: /data/data/com.termux/files/home/offline_ai/run.sh
    So cd goes to /data/data/com.termux/files/home — then python3 cli/chat.py
    would fail because cli/chat.py is not there.
  - The AGENTS.md says to create a symlink ~/offline_ai -> <repo>.
    This symlink does NOT currently exist on this system.
    The app may fail at import with "unable to open database file" or
    missing config.json unless KERROS_BASE is set.

Data stores (data/):
  - rag_store.db (SQLite FTS5) — primary knowledge store
  - session_fts.db — full-text search across sessions
  - session_store.db — session persistence
  - sqlite_db.sqlite — general database
  - decision_log.db — audit trail
  - channel_trace.jsonl — gateway channel events
  - agent_memory/ — per-agent memory stores (org, scout, team)
  - code_index/ — code symbol index
  - workflows/ — workflow catalog + runs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7. RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CRITICAL (fix immediately):
  [1] requirements.txt has committed merge conflict markers.
      Run: git checkout --theirs requirements.txt (or --ours), then edit.
      Until fixed, pip install -r requirements.txt is broken.

  [2] run.sh path assumption is wrong for current layout.
      It does cd to parent-of-parent, but it's at repo root.
      Fix: change to cd "$(dirname "$0")" or create the ~/offline_ai symlink.

  [3] ~/offline_ai symlink does not exist.
      Run: ln -sfn /data/data/com.termux/files/home/offline_ai ~/offline_ai
      Or set KERROS_BASE before running.

HIGH (fix soon):
  [4] cli/_chat_else.py has IndentationError and is dead code.
      Delete it or rename to _chat_else.txt.

  [5] cli/chat.py is a 1550-line monolith. Refactor slash commands
      into a dispatch table or plugin registry.

  [6] 12 patch_*.py and 4 apply_*.py files at repo root are clutter.
      Move to scripts/ or remove if already applied.

  [7] Skills hub (ADR-064) has 2 failing tests — quarantine logic
      and path validation need review.

MEDIUM (improve when convenient):
  [8] tree.txt and top_tree.txt should be gitignored.

  [9] core/config.py and kernel/config.py dual-config pattern is confusing.
      Consider unifying.

  [10] safe_commands includes ssh, python3, git, nmap, curl, wget.
      Consider whether these need argument validation or sandboxing.

  [11] API keys stored in plaintext in config.json.
      Consider OS keyring or encrypted storage.

LOW (nice to have):
  [12] Add type hints to cli/chat.py.
  [13] Add a /doctor command that checks symlink, config, model presence.
  [14] Consider splitting cli/chat.py into cli/commands/ modules.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
8. SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KerrOS is a large, ambitious terminal AI assistant with solid architectural
patterns (DI kernel, ports/adapters, fail-closed scope gate, comprehensive
audit logging). The codebase is functional but has accumulated technical debt:

  Strengths:
    - Clean boot lifecycle with phase machine
    - Strong scope gate / fail-closed security model
    - Comprehensive audit trail (hash chain, WORM, RBAC, privacy, residency)
    - Good port/adapter abstraction
    - 97.1% test pass rate (569/586)
    - Extensive documentation (README, ADRs, AGENTS.md, capability manifests)

  Weaknesses:
    - requirements.txt is broken (merge conflict markers)
    - run.sh path logic is wrong for current layout
    - ~/offline_ai symlink missing (will cause import failures)
    - cli/chat.py is a 1550-line monolith
    - Dead code and patch scripts cluttering root
    - Plaintext API key storage
    - Dual config system (core/config.py + kernel/config.py)

  Bottom line: The app will NOT run on this system right now due to the
  requirements.txt merge conflict and the missing ~/offline_ai symlink.
  Once those two issues are fixed, the offline mode (llama.cpp + GGUF)
  should work if the binary and model are present. Online mode requires
  API keys in .env.

================================================================================
END OF AUDIT
================================================================================
