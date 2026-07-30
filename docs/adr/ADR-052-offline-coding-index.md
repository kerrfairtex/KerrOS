# ADR-052: Offline Coding Index (ripgrep + tree-sitter Fake)

**Status:** Accepted  
**Date:** 2026-07-30

## Context

[ADR-050](ADR-050-offline-qwen05-profile.md) / [ADR-051](ADR-051-offline-rag-faiss.md)
shipped the offline LLM + RAG baseline. Phase C adds the **Coding
Assistant** surface: ripgrep content search + a soft symbol index,
without merging workspace AST into KerrOS RAG / OmniRoute memory.

## Decision

1. Allowlist **`rg`** in `config.json` `safe_commands`; offline profile
   `coding.ripgrep` also injects `rg` into the claw exec allowlist
2. Add **`adapters/code_index/code_index_adapter.py`** — Fake regex
   symbol extraction by default; soft `tree_sitter` import when present
   (grammars still operator-owned); persist under `data/code_index/`
3. Claw tools: `code_index_build`, `code_symbols`, `code_search`
4. CLI: `/code-index`, `/symbols`, `/code-search` (and `/rg`)
5. Register `code_index_port` at boot; health `probe_code_index`
6. Keep MemoryPort / RAG / OmniRoute separation intact

Out of scope: full tree-sitter language grammar packaging, IDE LSP,
ingesting code into `rag/store.py`, Unsloth fine-tune, LiteLLM gateway.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Only `/exec grep` | Profile asks for ripgrep; `rg` is faster/safer with globs |
| Merge symbols into HybridMemory | Breaks MEMORY_SEPARATION |
| Require tree-sitter in CI | Soft Fake regex required |

## Consequences

**Positive:** Coding assistant can search symbols/content offline via claw.

**Negative:** Fake symbols are regex-approximate; real AST needs grammars.

## Revisit when

Phase D (Unsloth LoRA→GGUF), Phase E (LiteLLM gateway), or funded
tree-sitter grammar bundles / LSP.
