"""
adapters/embeddings/resolve.py
===============================
Resolve embedding model / dimension from config + offline profile (ADR-051).
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

# Known dims — override via embedding_dim / KERROS_EMBEDDING_DIM.
KNOWN_DIMS: dict[str, int] = {
    "all-minilm-l6-v2": 384,
    "sentence-transformers/all-minilm-l6-v2": 384,
    "baai/bge-small-en-v1.5": 384,
    "nomic-ai/nomic-embed-text-v1.5": 768,
    "nomic-ai/nomic-embed-text-v1": 768,
}

DEFAULT_CLOUD_EMBED = "all-MiniLM-L6-v2"
DEFAULT_OFFLINE_EMBED = "nomic-ai/nomic-embed-text-v1.5"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _profile_embeddings(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = dict(cfg or {})
    try:
        from adapters.llm.offline_profile import (
            is_offline_profile_active,
            load_offline_profile,
        )

        if not is_offline_profile_active(data):
            return {}
        profile = load_offline_profile(cfg=data)
        emb = profile.get("embeddings") if isinstance(profile, dict) else None
        return dict(emb) if isinstance(emb, dict) else {}
    except Exception:
        return {}


def resolve_embedding_model(cfg: Mapping[str, Any] | None = None) -> str:
    data = dict(cfg or {})
    env = os.environ.get("KERROS_EMBEDDING_MODEL", "").strip()
    if env:
        return env
    if str(data.get("embedding_model") or "").strip():
        return str(data["embedding_model"]).strip()
    if str(data.get("qdrant_embedding_model") or "").strip():
        return str(data["qdrant_embedding_model"]).strip()
    profile_emb = _profile_embeddings(data)
    if str(profile_emb.get("model") or "").strip():
        return str(profile_emb["model"]).strip()
    # Offline profile active without explicit model → nomic.
    try:
        from adapters.llm.offline_profile import is_offline_profile_active

        if is_offline_profile_active(data):
            return DEFAULT_OFFLINE_EMBED
    except Exception:
        pass
    return DEFAULT_CLOUD_EMBED


def resolve_embedding_dim(
    model_name: Optional[str] = None,
    cfg: Mapping[str, Any] | None = None,
) -> int:
    data = dict(cfg or {})
    env = os.environ.get("KERROS_EMBEDDING_DIM", "").strip()
    if env.isdigit():
        return int(env)
    if data.get("embedding_dim") is not None:
        try:
            return int(data["embedding_dim"])
        except (TypeError, ValueError):
            pass
    name = (model_name or resolve_embedding_model(data)).strip()
    return KNOWN_DIMS.get(name.lower(), 384)


def resolve_embedding_prefixes(
    cfg: Mapping[str, Any] | None = None,
    *,
    model_name: Optional[str] = None,
) -> tuple[str, str]:
    """Return (query_prefix, document_prefix). Nomic gets search_* defaults."""
    data = dict(cfg or {})
    profile_emb = _profile_embeddings(data)
    q = (
        os.environ.get("KERROS_EMBEDDING_QUERY_PREFIX")
        or data.get("embedding_query_prefix")
        or profile_emb.get("query_prefix")
        or ""
    )
    d = (
        os.environ.get("KERROS_EMBEDDING_DOCUMENT_PREFIX")
        or data.get("embedding_document_prefix")
        or profile_emb.get("document_prefix")
        or ""
    )
    name = (model_name or resolve_embedding_model(data)).lower()
    if "nomic-embed" in name:
        if not str(q).strip():
            q = "search_query: "
        if not str(d).strip():
            d = "search_document: "
    return str(q), str(d)


def nomic_trust_remote_code(model_name: str) -> bool:
    return "nomic" in (model_name or "").lower()
