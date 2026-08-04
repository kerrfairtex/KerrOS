"""
CodeRagAdapter — Soft production-shaped code-RAG pipeline (ADR-107).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional

from kernel.flags import is_true
from adapters.code_rag.context import build_context
from adapters.code_rag.extract import extract_file
from adapters.code_rag.indexes import CodeRagIndexes
from adapters.code_rag.languages import CODE_EXTS
from adapters.code_rag.retrieve import hybrid_retrieve
from adapters.code_rag.scanner import scan_repository

try:
    from rag.path_guard import assert_kerros_memory_path
except Exception:  # pragma: no cover

    def assert_kerros_memory_path(path, label="path"):  # type: ignore
        return path


def is_code_rag_enabled(cfg: dict[str, Any] | None = None) -> bool:
    env = os.getenv("KERROS_CODE_RAG")
    if env is not None and str(env).strip() != "":
        return is_true(env)
    data = cfg or {}
    if "code_rag" in data and isinstance(data["code_rag"], dict):
        return is_true(data["code_rag"].get("enabled", False))
    return is_true(data.get("code_rag_enabled", False))


def resolve_code_rag_root(cfg: dict[str, Any] | None = None, *, base: Path | None = None) -> Path:
    data = cfg or {}
    block = data.get("code_rag") if isinstance(data.get("code_rag"), dict) else {}
    rel = (
        os.getenv("KERROS_CODE_RAG_PATH")
        or (block or {}).get("path")
        or data.get("code_rag_path")
        or "data/code_rag"
    )
    root_base = base or Path(os.path.expanduser("~/offline_ai"))
    path = Path(rel)
    if not path.is_absolute():
        path = root_base / path
    assert_kerros_memory_path(path, label="code_rag_path")
    return path


def probe_code_rag(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    enabled = is_code_rag_enabled(cfg)
    root = resolve_code_rag_root(cfg)
    stats = {}
    if root.is_dir():
        try:
            stats = CodeRagIndexes(root).stats()
        except Exception as exc:
            stats = {"error": str(exc)}
    return {
        "component": "code_rag",
        "enabled": enabled,
        "path": str(root),
        "adr": "ADR-107",
        **stats,
    }


class CodeRagAdapter:
    """LLMPort-adjacent Soft code-RAG: build / retrieve / build_context."""

    def __init__(self, config: dict[str, Any] | None = None, *, workspace: Path | None = None) -> None:
        self.cfg = dict(config or {})
        self.enabled = is_code_rag_enabled(self.cfg)
        self.workspace = (workspace or Path(os.path.expanduser("~/offline_ai"))).resolve()
        self.index_root = resolve_code_rag_root(self.cfg, base=self.workspace)
        self.indexes = CodeRagIndexes(self.index_root)

    def status(self) -> dict[str, Any]:
        st = self.indexes.stats()
        st.update(
            {
                "enabled": self.enabled,
                "workspace": str(self.workspace),
                "pipeline": [
                    "scanner",
                    "language_detect",
                    "extract",
                    "indexes(fts+symbol+graph+vector)",
                    "hybrid_retrieve",
                    "rerank",
                    "context+citations",
                ],
            }
        )
        return st

    def build(self, root: str | None = None, *, full: bool = False) -> dict[str, Any]:
        """Scan → extract → index. Incremental unless full=True."""
        t0 = time.time()
        ws = Path(root).resolve() if root else self.workspace
        prev = {} if full else self.indexes.load_manifest()
        scan = scan_repository(ws, previous=prev, extensions=CODE_EXTS | {".md", ".rst", ".toml", ".yaml", ".yml"})
        # remove deleted
        self.indexes.remove_paths(scan["removed"])
        to_process = scan["added"] + scan["changed"]
        if full:
            to_process = sorted(scan["files"].keys())
        processed = 0
        errors: list[str] = []
        for rel in to_process:
            path = ws / rel
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                errors.append(f"{rel}: {exc}")
                continue
            extracted = extract_file(rel, text)
            self.indexes.upsert_extraction(extracted)
            processed += 1

        manifest = {
            "root": str(ws),
            "files": scan["files"],
            "built_at": time.time(),
            "full": full,
        }
        self.indexes.save_manifest(manifest)
        stats = self.indexes.stats()
        return {
            "ok": True,
            "root": str(ws),
            "full": full,
            "scanned": len(scan["files"]),
            "processed": processed,
            "added": len(scan["added"]),
            "changed": len(scan["changed"]),
            "removed": len(scan["removed"]),
            "unchanged": len(scan["unchanged"]),
            "gitignore_patterns": scan.get("gitignore_patterns"),
            "errors": errors[:20],
            "stats": stats,
            "elapsed_s": round(time.time() - t0, 3),
        }

    def retrieve(self, query: str, *, top_k: int = 8) -> list[dict[str, Any]]:
        return hybrid_retrieve(self.indexes, query, top_k=top_k)

    def build_context(self, query: str, *, top_k: int = 8, budget: int = 3500) -> dict[str, Any]:
        return build_context(self.indexes, query, top_k=top_k, budget=budget)

    def ask(self, query: str, *, top_k: int = 8, use_llm: bool = False) -> dict[str, Any]:
        """Retrieve + optional Soft LLM completion via LLMPort/LiteLLM."""
        ctx = self.build_context(query, top_k=top_k)
        answer = None
        provider = None
        if use_llm:
            try:
                from kernel.access import get_llm_port

                port = get_llm_port()
                answer = port.complete(ctx["prompt"], max_tokens=1024)
                provider = getattr(port, "last_api_used", lambda: None)()
            except Exception as exc:
                answer = f"[code-rag llm soft-skip: {exc}]"
        return {
            "ok": True,
            "query": query,
            "citations": ctx.get("citations"),
            "hits": ctx.get("hits"),
            "context": ctx.get("context"),
            "answer": answer,
            "provider": provider,
            "intent": ctx.get("intent"),
        }
