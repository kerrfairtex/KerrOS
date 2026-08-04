# ADR-107: Production-Shaped Soft Code-RAG Pipeline

**Status:** Accepted  
**Date:** 2026-08-04

## Context

[ADR-052](ADR-052-offline-coding-index.md) shipped Fake symbols + ripgrep for
claw coding search. Operators need a **production-shaped** code-RAG pipeline
(scanner → parsers → knowledge extract → multi-index → hybrid retrieve →
rerank → context + citations → LLM), without merging workspace AST into
MemoryPort / OmniRoute ([MEMORY_SEPARATION](../MEMORY_SEPARATION.md)).

## Decision

1. Add Soft **`adapters/code_rag/`** pipeline under `data/code_rag/` (default
   off: `KERROS_CODE_RAG=1` or `code_rag.enabled`).
2. Stages (Soft/Fake in CI; real grammars/embeddings operator-owned):
   - **Scanner** — shallow walk, `.gitignore`-aware, binary/vendor skip,
     incremental mtime/hash re-index
   - **Language detect** — extension + shebang heuristics
   - **Extract** — function/class semantic chunks + symbol/graph edges
     (Fake regex; Soft tree-sitter when installed)
   - **Indexes** — SQLite FTS5 (BM25-ish), symbol/graph JSON, metadata,
     Soft vector slot (hash embedding; FAISS optional later)
   - **Retriever** — hybrid (FTS + symbols + graph neighbors) + Soft rerank
   - **Context builder** — token budget, dedupe, file:line citations
   - **LLM** — optional enrich via existing LiteLLM / LLMPort (Soft)
3. Register **`code_rag_port`**; claw `/code-rag`, `/code-ask`.
4. **Do not** ingest into `rag/store.py` / MemoryPort. ADR-052 remains the
   lightweight symbol/rg surface; ADR-107 is the fuller pipeline Soft.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Expand ADR-052 only | 052 decision is claw Soft index + Memory separation; pipeline needs own ADR |
| Merge into HybridMemory | Breaks MEMORY_SEPARATION |
| Require tree-sitter + FAISS in CI | Soft Fake required |

## Consequences

**Positive:** Diff-friendly re-index, hybrid code search, citations; path to
funded AST/vector later without rewriting claw tools.

**Negative:** Fake AST/graph approximate; Soft vectors are not semantic until
EmbeddingPort is wired for code.

## Revisit when

Funded Tree-sitter grammar bundles, production embedding model for code, or
LSP-backed graph index.
