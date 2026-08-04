"""
Context builder with citations (ADR-107 Soft).
"""

from __future__ import annotations

from typing import Any

from adapters.code_rag.indexes import CodeRagIndexes
from adapters.code_rag.retrieve import hybrid_retrieve


def _load_chunk_body(indexes: CodeRagIndexes, chunk_id: str) -> str:
    if not chunk_id:
        return ""
    # pull from FTS
    import sqlite3

    try:
        conn = sqlite3.connect(indexes.db_path)
        row = conn.execute(
            "SELECT body, docstring FROM chunks_fts WHERE chunk_id = ? LIMIT 1",
            (chunk_id,),
        ).fetchone()
        conn.close()
        if not row:
            return ""
        body, doc = row[0] or "", row[1] or ""
        if doc:
            return f"{doc}\n\n{body}"[:4000]
        return body[:4000]
    except Exception:
        return ""


def build_context(
    indexes: CodeRagIndexes,
    query: str,
    *,
    top_k: int = 8,
    budget: int = 3500,
) -> dict[str, Any]:
    hits = hybrid_retrieve(indexes, query, top_k=top_k)
    parts: list[str] = []
    citations: list[str] = []
    used = 0
    seen_paths: set[str] = set()

    for hit in hits:
        cite = hit.get("citation") or hit.get("path") or ""
        path = hit.get("path") or ""
        body = _load_chunk_body(indexes, hit.get("chunk_id") or "")
        if not body:
            body = hit.get("snippet") or hit.get("name") or ""
        # dependency expansion Soft: if same path already large, skip dup
        key = f"{path}:{hit.get('name')}"
        if key in seen_paths:
            continue
        seen_paths.add(key)
        block = (
            f"### {hit.get('name') or path} ({hit.get('kind') or 'chunk'})\n"
            f"Source: {cite}\n"
            f"Signals: {', '.join(hit.get('sources') or [])}\n"
            f"```\n{body[:1200]}\n```\n"
        )
        if used + len(block) > budget:
            break
        parts.append(block)
        if cite:
            citations.append(cite)
        used += len(block)

    prompt = (
        "You are answering a question about a code repository. "
        "Cite file:line ranges from the Sources below.\n\n"
        f"Question: {query}\n\n"
        "Retrieved context:\n" + ("\n".join(parts) if parts else "(no hits — rebuild with /code-rag build)")
    )
    return {
        "ok": True,
        "query": query,
        "intent": hits[0].get("intent") if hits else "find",
        "hits": hits,
        "citations": citations,
        "context": "\n".join(parts),
        "prompt": prompt,
        "chars": used,
        "budget": budget,
    }
