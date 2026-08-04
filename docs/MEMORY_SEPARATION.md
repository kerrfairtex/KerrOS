# KerrOS ↔ OmniRoute memory separation (README P5)

> Different jobs, don't merge. OmniRoute's FTS5+vector memory stays inside
> OmniRoute. KerrOS RAG / chat memory stays under KerrOS `data/`.

| System | Store | Job |
|--------|-------|-----|
| **KerrOS RAG** | `{KERROS_BASE}/data/rag_store.db` (SQLite FTS5) | Cyber knowledge retrieval for agents (`agent:knowledge`, MemoryPort) |
| **KerrOS chat memory** | `data/memory.json`, `data/profile.json`, `data/semantic.json`, `data/episodic.json` | Session / profile / learned facts |
| **KerrOS vectors (optional)** | Qdrant collection `kerros_memory` | Hybrid recall beside KerrOS FTS — never OmniRoute collections |
| **KerrOS code index (ADR-052)** | `data/code_index/` | Workspace symbols + ripgrep — not MemoryPort |
| **KerrOS code-RAG (ADR-107)** | `data/code_rag/` | Soft hybrid code pipeline (FTS/graph/vector Soft) — not MemoryPort |
| **OmniRoute** | Docker volume `kerros-omniroute-data` → container `/app/data` (`DATA_DIR`) | Gateway routing, provider catalog, OmniRoute's own memory |

OmniRoute is a KerrOS **LLM provider** (`provider:omniroute` / `OMNIROUTE_ENDPOINT`).
It is **not** a MemoryPort backend and must not share SQLite/FTS/Qdrant with KerrOS.

## Forbidden

- Mounting KerrOS `data/` into the OmniRoute container (or the reverse)
- Pointing `rag_store.db`, `knowledge_root`, or `knowledge_index` at `deploy/omniroute/` or OmniRoute `DATA_DIR`
- Reusing OmniRoute Qdrant/collection names for `qdrant_collection` (keep `kerros_memory`)
- Ingesting OmniRoute gateway DB files into KerrOS RAG “to unify memory”

## Enforcement

- Runtime: `rag/path_guard.py` refuses OmniRoute path markers for KerrOS RAG paths
- Static: `python3 scripts/check_memory_separation.py`
- Capability metadata: `provider:omniroute` → `memory_boundary: separate`

## Related

- Deploy kit: [`deploy/omniroute/`](../deploy/omniroute/)
- Qdrant sidecar (C-18): [`deploy/qdrant/`](../deploy/qdrant/) ([ADR-015](adr/ADR-015-qdrant-optional-vector-store.md))
- Security audit (AES keys ≠ KerrOS `ENCRYPTION_KEY`): [`OMNIROUTE_SECURITY_AUDIT.md`](OMNIROUTE_SECURITY_AUDIT.md)
