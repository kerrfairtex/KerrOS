"""
memory/unified_store.py
=======================
Unified multi-agent memory (ADR-106).

Named file-backed stores under data/agent_memory/stores/<name>/ with:
  - attach scopes per session (read | read_write)
  - optimistic concurrency via content_sha256 preconditions
  - version history + session/agent attribution
  - prompt snapshots from attached stores

ON BY DEFAULT when kerros_memory.enabled is True (kernel default).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

BASE = Path(os.path.expanduser("~/offline_ai"))
ROOT = BASE / "data" / "agent_memory"
STORES = ROOT / "stores"
VERSIONS = ROOT / "versions"
META = ROOT / "meta.json"
ATTACH = ROOT / "attachments.json"

ACCESS_READ = "read"
ACCESS_RW = "read_write"
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
_SAFE_REL = re.compile(r"^(?:[a-zA-Z0-9_.-]+/)*[a-zA-Z0-9_.-]+$")

_lock = threading.RLock()
_initialized = False


def _root() -> Path:
    ROOT.mkdir(parents=True, exist_ok=True)
    STORES.mkdir(parents=True, exist_ok=True)
    VERSIONS.mkdir(parents=True, exist_ok=True)
    return ROOT


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def is_enabled() -> bool:
    env = os.environ.get("KERROS_MEMORY", "").strip().lower()
    if env in ("0", "false", "off", "no"):
        return False
    if env in ("1", "true", "on", "yes"):
        return True
    try:
        from kernel.config import load_config

        cfg = load_config()
        block = cfg.get("kerros_memory") or {}
        if isinstance(block, dict):
            return bool(block.get("enabled", True))
    except Exception:
        pass
    return True


def _validate_store(name: str) -> str:
    name = (name or "").strip()
    if not _SAFE_NAME.match(name):
        raise ValueError(f"invalid store name: {name!r}")
    return name


def _validate_rel(rel: str) -> str:
    rel = (rel or "").strip().lstrip("./").replace("\\", "/")
    if not rel or ".." in rel.split("/") or not _SAFE_REL.match(rel):
        raise ValueError(f"invalid memory path: {rel!r}")
    return rel


def _store_dir(name: str) -> Path:
    return STORES / _validate_store(name)


def _file_path(store: str, rel: str) -> Path:
    return _store_dir(store) / _validate_rel(rel)


def _version_dir(store: str, rel: str) -> Path:
    key = hashlib.sha1(f"{store}:{rel}".encode()).hexdigest()[:16]
    return VERSIONS / store / key


def _meta() -> dict[str, Any]:
    _root()
    data = _load_json(META, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("stores", {})
    return data


def _save_meta(meta: dict[str, Any]) -> None:
    _save_json(META, meta)


def register_store(
    name: str,
    *,
    default_access: str = ACCESS_RW,
    description: str = "",
    readonly: bool = False,
) -> dict[str, Any]:
    name = _validate_store(name)
    if default_access not in (ACCESS_READ, ACCESS_RW):
        return {"ok": False, "error": "default_access must be read|read_write"}
    with _lock:
        meta = _meta()
        entry = meta["stores"].get(name) or {}
        entry.update(
            {
                "name": name,
                "default_access": ACCESS_READ if readonly else default_access,
                "readonly": bool(readonly),
                "description": description or entry.get("description") or "",
                "updated_at": time.time(),
            }
        )
        if "created_at" not in entry:
            entry["created_at"] = time.time()
        meta["stores"][name] = entry
        _store_dir(name).mkdir(parents=True, exist_ok=True)
        _save_meta(meta)
        return {"ok": True, "store": entry}


def list_stores() -> list[dict[str, Any]]:
    with _lock:
        meta = _meta()
        return sorted(meta["stores"].values(), key=lambda s: s.get("name") or "")


def _attachments() -> dict[str, Any]:
    _root()
    data = _load_json(ATTACH, {})
    return data if isinstance(data, dict) else {}


def attach(
    session_id: str,
    store: str,
    access: str = ACCESS_RW,
    *,
    agent: str = "",
) -> dict[str, Any]:
    session_id = (session_id or "").strip() or "default"
    store = _validate_store(store)
    if access not in (ACCESS_READ, ACCESS_RW):
        return {"ok": False, "error": "access must be read|read_write"}
    with _lock:
        meta = _meta()
        info = meta["stores"].get(store)
        if not info:
            return {"ok": False, "error": f"unknown store: {store}"}
        if info.get("readonly") and access == ACCESS_RW:
            access = ACCESS_READ
        data = _attachments()
        sess = data.setdefault(session_id, {"stores": {}, "agent": agent or ""})
        if agent:
            sess["agent"] = agent
        sess["stores"][store] = {"access": access, "attached_at": time.time()}
        _save_json(ATTACH, data)
        return {"ok": True, "session_id": session_id, "store": store, "access": access}


def detach(session_id: str, store: str) -> dict[str, Any]:
    session_id = (session_id or "").strip() or "default"
    store = _validate_store(store)
    with _lock:
        data = _attachments()
        sess = data.get(session_id) or {}
        stores = sess.get("stores") or {}
        stores.pop(store, None)
        if stores:
            sess["stores"] = stores
            data[session_id] = sess
        else:
            data.pop(session_id, None)
        _save_json(ATTACH, data)
        return {"ok": True, "session_id": session_id, "store": store}


def list_attached(session_id: str) -> list[dict[str, Any]]:
    session_id = (session_id or "").strip() or "default"
    with _lock:
        sess = (_attachments().get(session_id) or {})
        out = []
        for name, info in (sess.get("stores") or {}).items():
            out.append({"store": name, "access": info.get("access"), "agent": sess.get("agent")})
        return out


def _session_access(session_id: str, store: str) -> Optional[str]:
    sess = (_attachments().get(session_id) or {})
    info = (sess.get("stores") or {}).get(store)
    if not info:
        return None
    return info.get("access")


def read(
    store: str,
    rel: str,
    *,
    session_id: str = "",
    agent: str = "",
) -> dict[str, Any]:
    store = _validate_store(store)
    rel = _validate_rel(rel)
    with _lock:
        if session_id:
            access = _session_access(session_id, store)
            if access is None:
                return {"ok": False, "error": "store not attached", "store": store}
        path = _file_path(store, rel)
        if not path.is_file():
            return {
                "ok": True,
                "exists": False,
                "store": store,
                "path": rel,
                "content": "",
                "sha256": _sha(""),
                "version": 0,
            }
        content = path.read_text(encoding="utf-8")
        hist = _history_unlocked(store, rel)
        version = hist[-1]["version"] if hist else 1
        return {
            "ok": True,
            "exists": True,
            "store": store,
            "path": rel,
            "content": content,
            "sha256": _sha(content),
            "version": version,
            "agent": agent or None,
        }


def _history_unlocked(store: str, rel: str) -> list[dict[str, Any]]:
    index = _version_dir(store, rel) / "index.json"
    data = _load_json(index, [])
    return data if isinstance(data, list) else []


def history(store: str, rel: str) -> list[dict[str, Any]]:
    store = _validate_store(store)
    rel = _validate_rel(rel)
    with _lock:
        return list(_history_unlocked(store, rel))


def write(
    store: str,
    rel: str,
    content: str,
    *,
    expected_sha256: Optional[str] = None,
    session_id: str = "",
    agent: str = "",
    reason: str = "",
    system: bool = False,
) -> dict[str, Any]:
    store = _validate_store(store)
    rel = _validate_rel(rel)
    content = content if content is not None else ""
    with _lock:
        meta = _meta()
        info = meta["stores"].get(store)
        if not info:
            return {"ok": False, "error": f"unknown store: {store}"}
        # Agents cannot write org/read-only stores; seed/system may.
        if info.get("readonly") and not system:
            return {"ok": False, "error": "store is read-only", "store": store}
        if session_id:
            access = _session_access(session_id, store)
            if access is None:
                return {"ok": False, "error": "store not attached", "store": store}
            if access != ACCESS_RW:
                return {"ok": False, "error": "read-only attach", "store": store}

        path = _file_path(store, rel)
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        current_sha = _sha(current)
        if expected_sha256 is not None and expected_sha256 != current_sha:
            return {
                "ok": False,
                "error": "conflict",
                "conflict": True,
                "store": store,
                "path": rel,
                "expected_sha256": expected_sha256,
                "current_sha256": current_sha,
                "hint": "re-read and retry with current sha256",
            }

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        new_sha = _sha(content)
        hist = _history_unlocked(store, rel)
        version = (hist[-1]["version"] + 1) if hist else 1
        record = {
            "version": version,
            "sha256": new_sha,
            "prev_sha256": current_sha,
            "session_id": session_id or None,
            "agent": agent or None,
            "reason": (reason or "").strip() or None,
            "ts": time.time(),
            "bytes": len(content.encode("utf-8")),
        }
        vdir = _version_dir(store, rel)
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / f"v{version}.md").write_text(content, encoding="utf-8")
        hist.append(record)
        _save_json(vdir / "index.json", hist)
        return {
            "ok": True,
            "store": store,
            "path": rel,
            "sha256": new_sha,
            "version": version,
            "session_id": session_id or None,
            "agent": agent or None,
        }


def rollback(
    store: str,
    rel: str,
    version: int,
    *,
    session_id: str = "",
    agent: str = "",
    reason: str = "",
) -> dict[str, Any]:
    store = _validate_store(store)
    rel = _validate_rel(rel)
    with _lock:
        hist = _history_unlocked(store, rel)
        match = next((h for h in hist if h.get("version") == int(version)), None)
        if not match:
            return {"ok": False, "error": f"version {version} not found"}
        blob = _version_dir(store, rel) / f"v{int(version)}.md"
        if not blob.is_file():
            return {"ok": False, "error": "version blob missing"}
        content = blob.read_text(encoding="utf-8")
    return write(
        store,
        rel,
        content,
        session_id=session_id,
        agent=agent,
        reason=reason or f"rollback to v{version}",
    )


def list_files(store: str) -> list[str]:
    store = _validate_store(store)
    root = _store_dir(store)
    if not root.is_dir():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != ".gitkeep":
            out.append(str(p.relative_to(root)).replace("\\", "/"))
    return out


def snapshot_for_prompt(session_id: str, *, budget: int = 3500) -> str:
    """Render attached store files for LLM context (newest-small-files first)."""
    if not is_enabled():
        return ""
    session_id = (session_id or "").strip() or "default"
    parts: list[str] = []
    used = 0
    with _lock:
        attached = list_attached(session_id)
        if not attached:
            # default: scout preferences if present
            attached = [{"store": "scout", "access": ACCESS_READ}]
        for item in attached:
            store = item["store"]
            header = f"[Agent memory:{store} ({item.get('access')})]"
            files = list_files(store)
            # Prefer preference / task / notes over large dumps
            prefer = sorted(
                files,
                key=lambda f: (
                    0
                    if any(k in f for k in ("preference", "contact", "account", "deploy", "convention"))
                    else 1,
                    len(f),
                ),
            )
            block_lines = [header]
            for rel in prefer[:12]:
                path = _file_path(store, rel)
                try:
                    text = path.read_text(encoding="utf-8").strip()
                except Exception:
                    continue
                if not text:
                    continue
                chunk = f"## {rel}\n{text[:800]}"
                if used + len(chunk) > budget:
                    break
                block_lines.append(chunk)
                used += len(chunk)
            if len(block_lines) > 1:
                parts.append("\n".join(block_lines))
    return "\n\n".join(parts)


def current_session_id() -> str:
    try:
        from memory.session_store import get_current_session_id

        sid = get_current_session_id()
        if sid:
            return str(sid)
    except Exception:
        pass
    return "default"


def ensure_defaults() -> dict[str, Any]:
    """Idempotent seed of org/team/scout stores + Scout inbox layout."""
    global _initialized
    with _lock:
        _root()
        from memory.scout_defaults import seed_all

        result = seed_all()
        _initialized = True
        return result


def bootstrap_session(session_id: str = "", *, agent: str = "kerros") -> dict[str, Any]:
    """Ensure defaults and attach default stores for a session (ON by default)."""
    if not is_enabled():
        return {"ok": False, "enabled": False}
    sid = (session_id or "").strip() or current_session_id()
    ensure_defaults()
    attached = []
    for store, access in (
        ("org", ACCESS_READ),
        ("team", ACCESS_RW),
        ("scout", ACCESS_RW),
    ):
        out = attach(sid, store, access, agent=agent)
        attached.append(out)
    return {"ok": True, "enabled": True, "session_id": sid, "attached": attached}
