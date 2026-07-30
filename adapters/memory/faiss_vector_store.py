"""
adapters/memory/faiss_vector_store.py
=====================================
Optional FAISS / numpy vector recall for HybridMemoryAdapter (ADR-051).

SQLite FTS remains primary. Default-off. Soft ``faiss`` when installed;
numpy cosine index Fake otherwise (CI-safe, no GPU).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

from adapters.embeddings.resolve import resolve_embedding_dim, resolve_embedding_model
from adapters.embeddings.sentence_transformers_adapter import SentenceTransformersAdapter
from kernel.flags import is_true

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:  # pragma: no cover
    np = None  # type: ignore
    HAS_NUMPY = False

try:
    import faiss  # type: ignore

    HAS_FAISS = True
except ImportError:
    faiss = None  # type: ignore
    HAS_FAISS = False


def is_faiss_enabled(cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or {}
    env = os.getenv("KERROS_FAISS_ENABLED")
    if env is not None and str(env).strip() != "":
        return is_true(env)
    if "faiss_enabled" in data:
        return is_true(data.get("faiss_enabled"))
    # Offline profile with vector.optional=faiss opts in by default (ADR-051).
    try:
        from adapters.llm.offline_profile import (
            is_offline_profile_active,
            load_offline_profile,
        )

        if not is_offline_profile_active(data):
            return False
        profile = load_offline_profile(cfg=data)
        vector = profile.get("vector") if isinstance(profile, dict) else None
        if not isinstance(vector, dict):
            return False
        if vector.get("enabled") is False:
            return False
        optional = str(vector.get("optional") or "").strip().lower()
        return optional == "faiss"
    except Exception:
        return False
    return False

def resolve_faiss_index_path(
    cfg: dict[str, Any] | None = None,
    *,
    base: Optional[Path] = None,
) -> Path:
    data = cfg or {}
    profile_path = ""
    try:
        from adapters.llm.offline_profile import (
            is_offline_profile_active,
            load_offline_profile,
        )

        if is_offline_profile_active(data):
            profile = load_offline_profile(cfg=data)
            vector = profile.get("vector") if isinstance(profile, dict) else None
            if isinstance(vector, dict):
                profile_path = str(vector.get("index_path") or "").strip()
    except Exception:
        profile_path = ""
    raw = (
        os.getenv("KERROS_FAISS_INDEX_PATH")
        or data.get("faiss_index_path")
        or profile_path
        or "data/faiss/kerros_memory.npz"
    )
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        root = base
        if root is None:
            try:
                from kernel.config import load_config

                root = load_config().base
            except Exception:
                root = Path.home() / "offline_ai"
        path = Path(root) / path
    from rag.path_guard import assert_kerros_memory_path

    assert_kerros_memory_path(path, label="faiss_index_path")
    return path


def probe_faiss(config: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        from kernel.config import load_config

        cfg = dict(config or load_config().values)
    except Exception:
        cfg = dict(config or {})
    enabled = is_faiss_enabled(cfg)
    path = resolve_faiss_index_path(cfg)
    available = enabled and (HAS_NUMPY or HAS_FAISS)
    return {
        "component": "faiss",
        "enabled": enabled,
        "available": bool(available),
        "path": str(path),
        "has_faiss": HAS_FAISS,
        "has_numpy": HAS_NUMPY,
        "status": (
            "ok"
            if available
            else ("disabled" if not enabled else "unavailable")
        ),
    }


def _cosine_scores(matrix: Any, query: Any) -> Any:
    # matrix (n, d), query (d,)
    q = query.astype("float32")
    q_norm = float(np.linalg.norm(q) + 1e-12)
    m_norm = np.linalg.norm(matrix, axis=1) + 1e-12
    return (matrix @ q) / (m_norm * q_norm)


class FaissVectorStore:
    """Soft FAISS / numpy vector store. No-op when disabled."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        embedder: SentenceTransformersAdapter | None = None,
        base: Optional[Path] = None,
    ) -> None:
        cfg = dict(config or {})
        self.enabled = is_faiss_enabled(cfg)
        self.path = resolve_faiss_index_path(cfg, base=base)
        self.model_name = resolve_embedding_model(cfg)
        self.dimension = resolve_embedding_dim(self.model_name, cfg)
        self._embedder = embedder or SentenceTransformersAdapter(
            model_name=self.model_name, dimension=self.dimension, config=cfg
        )
        self.dimension = int(getattr(self._embedder, "dimension", self.dimension))
        self.backend = "faiss" if (self.enabled and HAS_FAISS) else "numpy"
        self.last_error = ""
        self._lock = threading.Lock()
        self._vectors: Any = None  # np.ndarray (n, d)
        self._meta: list[dict[str, Any]] = []
        self._index = None  # faiss index when available
        if self.enabled:
            self._load()

    def _empty_matrix(self) -> Any:
        if not HAS_NUMPY:
            return None
        return np.zeros((0, self.dimension), dtype="float32")

    def _load(self) -> None:
        if not HAS_NUMPY:
            self.last_error = "numpy not installed"
            return
        meta_path = self.path.with_suffix(".meta.json")
        if self.path.is_file():
            try:
                data = np.load(self.path, allow_pickle=False)
                self._vectors = data["vectors"].astype("float32")
                if self._vectors.ndim != 2 or self._vectors.shape[1] != self.dimension:
                    # Dim mismatch — start fresh (nomic vs MiniLM).
                    self._vectors = self._empty_matrix()
                    self._meta = []
                    self.last_error = "dimension mismatch — rebuilt empty index"
                else:
                    if meta_path.is_file():
                        self._meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    else:
                        self._meta = []
                    self.last_error = ""
            except Exception as exc:
                self._vectors = self._empty_matrix()
                self._meta = []
                self.last_error = str(exc)
        else:
            self._vectors = self._empty_matrix()
            self._meta = []
        self._rebuild_faiss()

    def _rebuild_faiss(self) -> None:
        self._index = None
        if not (HAS_FAISS and HAS_NUMPY and self._vectors is not None):
            return
        try:
            index = faiss.IndexFlatIP(self.dimension)
            if len(self._vectors):
                # Normalize for cosine via inner product.
                norms = np.linalg.norm(self._vectors, axis=1, keepdims=True) + 1e-12
                normalized = (self._vectors / norms).astype("float32")
                index.add(normalized)
            self._index = index
            self.backend = "faiss"
        except Exception as exc:
            self.last_error = str(exc)
            self.backend = "numpy"

    def _persist(self) -> None:
        if not HAS_NUMPY or self._vectors is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.path, vectors=self._vectors.astype("float32"))
        meta_path = self.path.with_suffix(".meta.json")
        meta_path.write_text(
            json.dumps(self._meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def upsert(
        self,
        chunks: list[str],
        source: str,
        metadata: dict[str, Any] | None = None,
        *,
        indices: list[int] | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        if not HAS_NUMPY:
            self.last_error = "numpy not installed"
            return False
        texts = [c for c in chunks if c]
        if not texts:
            return True
        try:
            vectors = self._embedder.embed_documents(texts)
            arr = np.asarray(vectors, dtype="float32")
            if arr.ndim != 2:
                arr = arr.reshape(len(texts), -1)
            with self._lock:
                if self._vectors is None or self._vectors.size == 0:
                    self._vectors = arr
                else:
                    self._vectors = np.vstack([self._vectors, arr])
                for i, chunk in enumerate(texts):
                    idx = indices[i] if indices and i < len(indices) else len(self._meta)
                    self._meta.append(
                        {
                            "source": source,
                            "chunk": chunk,
                            "idx": idx,
                            "metadata": metadata or {},
                        }
                    )
                self._rebuild_faiss()
                self._persist()
                self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def query(self, text: str, top_k: int = 5) -> list[tuple[float, str, str]]:
        if not self.enabled or not HAS_NUMPY:
            return []
        with self._lock:
            if self._vectors is None or len(self._vectors) == 0 or not self._meta:
                return []
            try:
                q = np.asarray(self._embedder.embed_query(text), dtype="float32")
                if self._index is not None and HAS_FAISS:
                    qn = q / (float(np.linalg.norm(q)) + 1e-12)
                    scores, idxs = self._index.search(
                        qn.reshape(1, -1).astype("float32"), min(top_k, len(self._meta))
                    )
                    out: list[tuple[float, str, str]] = []
                    for score, i in zip(scores[0].tolist(), idxs[0].tolist()):
                        if i < 0 or i >= len(self._meta):
                            continue
                        meta = self._meta[i]
                        out.append((float(score), meta["chunk"], meta["source"]))
                    return out
                scores = _cosine_scores(self._vectors, q)
                order = np.argsort(-scores)[:top_k]
                out = []
                for i in order.tolist():
                    meta = self._meta[i]
                    out.append((float(scores[i]), meta["chunk"], meta["source"]))
                return out
            except Exception as exc:
                self.last_error = str(exc)
                return []

    def status(self) -> dict[str, Any]:
        n = 0 if self._vectors is None else int(getattr(self._vectors, "shape", [0])[0])
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "path": str(self.path),
            "dimension": self.dimension,
            "model": self.model_name,
            "vectors": n,
            "has_faiss": HAS_FAISS,
            "last_error": self.last_error,
            "ready": bool(self.enabled and HAS_NUMPY),
        }
