"""
Multi-index store for code-RAG (ADR-107 Soft).

- SQLite FTS5 keyword index
- Symbol / graph JSON
- Metadata store
- Soft vector slot (hash embedding; optional FAISS later)
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

_lock = threading.RLock()


def _hash_embed(text: str, dim: int = 64) -> list[float]:
    """Deterministic Soft embedding (not semantic — CI-safe)."""
    vec = [0.0] * dim
    tokens = (text or "").lower().split()
    if not tokens:
        return vec
    for tok in tokens:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class CodeRagIndexes:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "fts.db"
        self.symbols_path = self.root / "symbols.json"
        self.graph_path = self.root / "graph.json"
        self.meta_path = self.root / "metadata.json"
        self.manifest_path = self.root / "manifest.json"
        self.vectors_path = self.root / "vectors.json"
        self._ensure_db()

    def _ensure_db(self) -> None:
        with _lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        path,
                        name,
                        kind,
                        language,
                        citation UNINDEXED,
                        docstring,
                        body,
                        tokenize='porter'
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"files": {}}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {"files": {}}

    def save_manifest(self, data: dict[str, Any]) -> None:
        self.manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _save_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def remove_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        with _lock:
            conn = sqlite3.connect(self.db_path)
            try:
                for p in paths:
                    conn.execute("DELETE FROM chunks_fts WHERE path = ?", (p,))
                conn.commit()
            finally:
                conn.close()
            symbols = [s for s in self._load_json(self.symbols_path, []) if s.get("path") not in paths]
            self._save_json(self.symbols_path, symbols)
            graph = self._load_json(self.graph_path, {"edges": []})
            edges = [
                e
                for e in (graph.get("edges") or [])
                if e.get("path") not in paths and e.get("src") not in paths
            ]
            self._save_json(self.graph_path, {"edges": edges})
            meta = self._load_json(self.meta_path, {})
            for p in paths:
                meta.pop(p, None)
            self._save_json(self.meta_path, meta)
            vecs = self._load_json(self.vectors_path, {})
            # drop vectors for removed paths
            drop_ids = [cid for cid, v in vecs.items() if (v or {}).get("path") in paths]
            for cid in drop_ids:
                vecs.pop(cid, None)
            self._save_json(self.vectors_path, vecs)

    def upsert_extraction(self, extracted: dict[str, Any]) -> None:
        path = extracted["path"]
        with _lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("DELETE FROM chunks_fts WHERE path = ?", (path,))
                for ch in extracted.get("chunks") or []:
                    conn.execute(
                        """
                        INSERT INTO chunks_fts
                        (chunk_id, path, name, kind, language, citation, docstring, body)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ch["id"],
                            ch["path"],
                            ch.get("name") or "",
                            ch.get("kind") or "",
                            ch.get("language") or "",
                            ch.get("citation") or "",
                            ch.get("docstring") or "",
                            ch.get("text") or "",
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

            symbols = [s for s in self._load_json(self.symbols_path, []) if s.get("path") != path]
            symbols.extend(extracted.get("symbols") or [])
            self._save_json(self.symbols_path, symbols)

            graph = self._load_json(self.graph_path, {"edges": []})
            edges = [e for e in (graph.get("edges") or []) if e.get("path") != path]
            edges.extend(extracted.get("edges") or [])
            self._save_json(self.graph_path, {"edges": edges[-20000:]})

            meta = self._load_json(self.meta_path, {})
            meta[path] = extracted.get("metadata") or {}
            self._save_json(self.meta_path, meta)

            vecs = self._load_json(self.vectors_path, {})
            # clear old vectors for path
            for cid in [k for k, v in vecs.items() if (v or {}).get("path") == path]:
                vecs.pop(cid, None)
            for ch in extracted.get("chunks") or []:
                blob = f"{ch.get('name','')} {ch.get('docstring','')} {ch.get('text','')[:1200]}"
                vecs[ch["id"]] = {
                    "path": path,
                    "citation": ch.get("citation"),
                    "name": ch.get("name"),
                    "vec": _hash_embed(blob),
                }
            self._save_json(self.vectors_path, vecs)

    def fts_search(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        # escape FTS special chars lightly
        safe = " ".join(t for t in q.replace('"', " ").split() if t)
        if not safe:
            return []
        with _lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                try:
                    rows = conn.execute(
                        """
                        SELECT chunk_id, path, name, kind, language, citation, docstring,
                               snippet(chunks_fts, 7, '>>>', '<<<', '…', 16) AS snip,
                               bm25(chunks_fts) AS score
                        FROM chunks_fts
                        WHERE chunks_fts MATCH ?
                        ORDER BY score
                        LIMIT ?
                        """,
                        (safe, top_k),
                    ).fetchall()
                except sqlite3.OperationalError:
                    # fallback substring
                    rows = conn.execute(
                        """
                        SELECT chunk_id, path, name, kind, language, citation, docstring,
                               substr(body, 1, 160) AS snip, 0.0 AS score
                        FROM chunks_fts
                        WHERE body LIKE ? OR name LIKE ? OR path LIKE ?
                        LIMIT ?
                        """,
                        (f"%{safe}%", f"%{safe}%", f"%{safe}%", top_k),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def symbol_search(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        q = (query or "").lower().strip()
        if not q:
            return []
        symbols = self._load_json(self.symbols_path, [])
        hits = [s for s in symbols if q in (s.get("name") or "").lower()]
        hits.sort(key=lambda s: (0 if (s.get("name") or "").lower() == q else 1, s.get("name") or ""))
        return hits[:top_k]

    def graph_neighbors(self, name: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        name = (name or "").strip()
        if not name:
            return []
        edges = (self._load_json(self.graph_path, {"edges": []}).get("edges") or [])
        out = []
        for e in edges:
            if e.get("src") == name or e.get("dst") == name:
                out.append(e)
            if len(out) >= top_k:
                break
        return out

    def vector_search(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        qv = _hash_embed(query)
        vecs = self._load_json(self.vectors_path, {})
        scored = []
        for cid, meta in vecs.items():
            score = _cos(qv, meta.get("vec") or [])
            scored.append(
                {
                    "chunk_id": cid,
                    "path": meta.get("path"),
                    "name": meta.get("name"),
                    "citation": meta.get("citation"),
                    "score": score,
                    "source": "vector",
                }
            )
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    def stats(self) -> dict[str, Any]:
        symbols = self._load_json(self.symbols_path, [])
        graph = self._load_json(self.graph_path, {"edges": []})
        meta = self._load_json(self.meta_path, {})
        vecs = self._load_json(self.vectors_path, {})
        with _lock:
            conn = sqlite3.connect(self.db_path)
            try:
                n = conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0]
            except Exception:
                n = 0
            finally:
                conn.close()
        return {
            "chunks": n,
            "symbols": len(symbols),
            "edges": len(graph.get("edges") or []),
            "files": len(meta),
            "vectors": len(vecs),
            "root": str(self.root),
        }
