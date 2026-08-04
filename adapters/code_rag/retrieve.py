"""
Hybrid retriever + Soft rerank (ADR-107).

Merges FTS (BM25), symbol hits, vector Soft scores, and graph neighbors.
"""

from __future__ import annotations

import re
from typing import Any

from adapters.code_rag.indexes import CodeRagIndexes

_INTENT = [
    ("impact", re.compile(r"\b(impact|break|callers?|depend|who uses|blast)\b", re.I)),
    ("explain", re.compile(r"\b(explain|how does|what is|overview|summar)\b", re.I)),
    ("bug", re.compile(r"\b(bug|error|exception|fix|fail|traceback)\b", re.I)),
    ("find", re.compile(r"\b(find|where|locate|search|show me)\b", re.I)),
]


def detect_intent(query: str) -> str:
    for name, rx in _INTENT:
        if rx.search(query or ""):
            return name
    return "find"


def hybrid_retrieve(
    indexes: CodeRagIndexes,
    query: str,
    *,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    intent = detect_intent(query)
    fts = indexes.fts_search(query, top_k=top_k * 3)
    symbols = indexes.symbol_search(query, top_k=top_k * 2)
    vectors = indexes.vector_search(query, top_k=top_k * 2)

    merged: dict[str, dict[str, Any]] = {}

    def _add(key: str, item: dict[str, Any], score: float, source: str) -> None:
        cur = merged.get(key)
        if not cur or score > cur.get("score", -1e9):
            row = dict(item)
            row["score"] = score
            row["sources"] = list(set((cur or {}).get("sources", []) + [source]))
            row["intent"] = intent
            merged[key] = row
        else:
            cur["sources"] = list(set(cur.get("sources", []) + [source]))
            cur["score"] = cur.get("score", 0) + 0.05

    for i, hit in enumerate(fts):
        # bm25: lower is better in sqlite
        raw = float(hit.get("score") or 0)
        score = 10.0 / (1.0 + abs(raw)) + max(0, 3 - i * 0.1)
        key = hit.get("chunk_id") or f"{hit.get('path')}:{hit.get('name')}"
        _add(
            key,
            {
                "chunk_id": hit.get("chunk_id"),
                "path": hit.get("path"),
                "name": hit.get("name"),
                "kind": hit.get("kind"),
                "language": hit.get("language"),
                "citation": hit.get("citation"),
                "snippet": hit.get("snip") or hit.get("docstring") or "",
            },
            score,
            "bm25",
        )

    for i, hit in enumerate(symbols):
        score = 8.0 - i * 0.2
        if intent == "impact":
            score += 2.0
        key = hit.get("chunk_id") or f"{hit.get('path')}:{hit.get('name')}"
        _add(
            key,
            {
                "chunk_id": hit.get("chunk_id"),
                "path": hit.get("path"),
                "name": hit.get("name"),
                "kind": hit.get("kind"),
                "language": hit.get("language"),
                "citation": f"{hit.get('path')}:{hit.get('line')}",
                "snippet": "",
            },
            score,
            "symbol",
        )
        # graph expansion for impact / explain
        if intent in ("impact", "explain"):
            for edge in indexes.graph_neighbors(hit.get("name") or "", top_k=8):
                gkey = f"edge:{edge.get('src')}:{edge.get('dst')}:{edge.get('rel')}"
                _add(
                    gkey,
                    {
                        "chunk_id": edge.get("chunk_id"),
                        "path": edge.get("path") or hit.get("path"),
                        "name": f"{edge.get('src')} -{edge.get('rel')}→ {edge.get('dst')}",
                        "kind": "graph",
                        "citation": edge.get("path") or hit.get("path"),
                        "snippet": f"{edge.get('rel')} edge",
                    },
                    score - 1.5,
                    "graph",
                )

    for i, hit in enumerate(vectors):
        score = float(hit.get("score") or 0) * 6.0
        key = hit.get("chunk_id") or f"v:{i}"
        _add(
            key,
            {
                "chunk_id": hit.get("chunk_id"),
                "path": hit.get("path"),
                "name": hit.get("name"),
                "citation": hit.get("citation"),
                "snippet": "",
            },
            score,
            "vector",
        )

    ranked = sorted(merged.values(), key=lambda x: -float(x.get("score") or 0))
    # Soft rerank: prefer multi-source agreement + citation present
    for row in ranked:
        bonus = 0.4 * max(0, len(row.get("sources") or []) - 1)
        if row.get("citation"):
            bonus += 0.2
        if intent == "bug" and any(k in (row.get("snippet") or "").lower() for k in ("error", "except", "raise")):
            bonus += 0.5
        row["score"] = float(row.get("score") or 0) + bonus
        row["rerank"] = "soft_merge"
    ranked.sort(key=lambda x: -float(x.get("score") or 0))
    return ranked[:top_k]
