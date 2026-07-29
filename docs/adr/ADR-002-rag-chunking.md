# ADR-002: RAG Chunking Strategy — 120 words, 30-word overlap

**Status:** Accepted  

**Date:** 2026-07-20  
**Accepted:** 2026-07-29  
**Verified against:** `rag/store.py` `_chunk(text, size=120, overlap=30)` / `chunk_text(...)`

## Context
The RAG store was rebuilt from scratch after discovering the original was bloated with duplicate content. The corpus spans structured, technical cybersecurity sources — NIST, CWE (XML), CVE (JSON), Sigma rules (YAML), YARA rules, CISA KEV — plus general reference material (networking/Linux/programming docs, Wikipedia via kiwix-serve). These sources are dense and often short-form (a CVE entry, a Sigma rule) rather than long prose, which shapes what chunk size actually retrieves well.

## Decision
`rag/store.py` chunks content at **120 words with a 30-word overlap** between adjacent chunks, plus deduplication, keyword filtering, and phrase-match scoring layered on top. This grew the usable knowledge base from ~23K to ~238K chunks across 13 cybersecurity categories.

Hybrid recall (`adapters/memory/hybrid_memory_adapter.py`) and optional Qdrant (`adapters/memory/qdrant_vector_store.py`) sit on top of this chunking strategy; they do not change the chunk size defaults.

## Alternatives considered
- **Larger chunks (300–500+ words)** — more surrounding context per chunk, but risks diluting retrieval precision for structured entries (a CVE or CWE record) where the relevant detail is a small fragment, not a paragraph.
- **No overlap** — cheaper to store and index, but risks losing context exactly at chunk boundaries, which matters when a technical definition or rule spans a boundary.
- **Whole-document embedding** — infeasible on ~3.7GB RAM given the corpus size (238K chunks after dedup); also poor for CVE/CWE-style sources where documents are already short discrete records.

## Consequences
Smaller chunks at this scale (238K) mean more vectors to store and search — a real memory/index cost on constrained hardware, which is exactly why deduplication and keyword filtering exist alongside the chunking itself. The 30-word overlap trades some storage/index redundancy for preserving context across chunk boundaries.

## Revisit when
- RAG scale demands a full pgvector→Qdrant migration as the primary store — re-evaluate chunking alongside any storage backend change
- Retrieval precision/recall becomes a measured problem in practice, not just a theoretical one
