# KerrOS Qdrant sidecar (C-18)

Optional vector store for hybrid MemoryPort recall. SQLite FTS remains primary.

**ADR:** [`docs/adr/ADR-015-qdrant-optional-vector-store.md`](../../docs/adr/ADR-015-qdrant-optional-vector-store.md)  
**Separation:** [`docs/MEMORY_SEPARATION.md`](../../docs/MEMORY_SEPARATION.md) — collection must stay `kerros_memory` (or non-OmniRoute).

## Quickstart

```bash
# from repo root
./scripts/qdrant_docker.sh up
./scripts/qdrant_docker.sh probe

export KERROS_QDRANT_ENABLED=1
export KERROS_QDRANT_URL=http://127.0.0.1:6333
export KERROS_QDRANT_COLLECTION=kerros_memory

# Preview migration from SQLite RAG chunks
python3 scripts/migrate_sqlite_rag_to_qdrant.py --dry-run --limit 20
python3 scripts/migrate_sqlite_rag_to_qdrant.py --batch-size 64
```

## Security

- Host ports are **loopback-only** (`127.0.0.1:6333`). Do not publish
  `0.0.0.0:6333` on a public droplet without a reverse proxy / API key.
- Never point KerrOS at OmniRoute Qdrant collections.
