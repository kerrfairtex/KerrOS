"""
tools/memory_graph.py
=====================
Memory graph tool (ADR-106) — entities + relations for agent memory.

Complements bash (shell) so KerrOS remembers structured links across agents.
File-backed at data/agent_memory/graph.json.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

BASE = Path(os.path.expanduser("~/offline_ai"))
GRAPH_PATH = BASE / "data" / "agent_memory" / "graph.json"
_lock = threading.RLock()
_SAFE = re.compile(r"^[a-zA-Z0-9_@./+-]{1,128}$")


def _load() -> dict[str, Any]:
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not GRAPH_PATH.is_file():
        return {"nodes": {}, "edges": []}
    try:
        data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"nodes": {}, "edges": []}
        data.setdefault("nodes", {})
        data.setdefault("edges", [])
        return data
    except Exception:
        return {"nodes": {}, "edges": []}


def _save(data: dict[str, Any]) -> None:
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GRAPH_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(GRAPH_PATH)


def add_node(
    label: str,
    *,
    kind: str = "entity",
    props: Optional[dict[str, Any]] = None,
    session_id: str = "",
    agent: str = "",
) -> dict[str, Any]:
    label = (label or "").strip()
    if not label:
        return {"ok": False, "error": "label required"}
    with _lock:
        data = _load()
        for nid, node in data["nodes"].items():
            if node.get("label") == label and node.get("kind") == kind:
                return {"ok": True, "id": nid, "node": node, "exists": True}
        nid = uuid.uuid4().hex[:12]
        node = {
            "id": nid,
            "label": label,
            "kind": kind or "entity",
            "props": props or {},
            "session_id": session_id or None,
            "agent": agent or None,
            "ts": time.time(),
        }
        data["nodes"][nid] = node
        _save(data)
        return {"ok": True, "id": nid, "node": node, "exists": False}


def link(
    src: str,
    dst: str,
    *,
    rel: str = "related",
    session_id: str = "",
    agent: str = "",
) -> dict[str, Any]:
    src, dst = (src or "").strip(), (dst or "").strip()
    rel = (rel or "related").strip() or "related"
    if not src or not dst:
        return {"ok": False, "error": "src and dst required"}
    with _lock:
        data = _load()
        # resolve labels to ids if needed
        def _resolve(x: str) -> Optional[str]:
            if x in data["nodes"]:
                return x
            for nid, n in data["nodes"].items():
                if n.get("label") == x:
                    return nid
            return None

        sid, did = _resolve(src), _resolve(dst)
        if not sid:
            created = add_node(src, kind="entity", session_id=session_id, agent=agent)
            sid = created.get("id")
            data = _load()
        if not did:
            created = add_node(dst, kind="entity", session_id=session_id, agent=agent)
            did = created.get("id")
            data = _load()
        for e in data["edges"]:
            if e.get("src") == sid and e.get("dst") == did and e.get("rel") == rel:
                return {"ok": True, "edge": e, "exists": True}
        edge = {
            "id": uuid.uuid4().hex[:10],
            "src": sid,
            "dst": did,
            "rel": rel,
            "session_id": session_id or None,
            "agent": agent or None,
            "ts": time.time(),
        }
        data["edges"].append(edge)
        _save(data)
        return {"ok": True, "edge": edge, "exists": False}


def query(q: str = "", *, kind: str = "") -> dict[str, Any]:
    q = (q or "").strip().lower()
    kind = (kind or "").strip().lower()
    with _lock:
        data = _load()
        nodes = []
        for n in data["nodes"].values():
            if kind and (n.get("kind") or "").lower() != kind:
                continue
            if q and q not in (n.get("label") or "").lower():
                continue
            nodes.append(n)
        edges = data["edges"]
        if q:
            ids = {n["id"] for n in nodes}
            edges = [e for e in edges if e.get("src") in ids or e.get("dst") in ids]
        return {"ok": True, "nodes": nodes[:50], "edges": edges[:100]}


def neighbors(label_or_id: str) -> dict[str, Any]:
    label_or_id = (label_or_id or "").strip()
    with _lock:
        data = _load()
        nid = label_or_id if label_or_id in data["nodes"] else None
        if not nid:
            for i, n in data["nodes"].items():
                if n.get("label") == label_or_id:
                    nid = i
                    break
        if not nid:
            return {"ok": False, "error": "node not found"}
        related = []
        for e in data["edges"]:
            if e.get("src") == nid:
                related.append({"direction": "out", "rel": e.get("rel"), "node": data["nodes"].get(e["dst"])})
            elif e.get("dst") == nid:
                related.append({"direction": "in", "rel": e.get("rel"), "node": data["nodes"].get(e["src"])})
        return {"ok": True, "id": nid, "node": data["nodes"][nid], "neighbors": related}


def remember_entities(
    labels: list[str],
    *,
    kind: str = "entity",
    session_id: str = "",
    agent: str = "",
) -> dict[str, Any]:
    created = []
    for label in labels:
        out = add_node(label, kind=kind, session_id=session_id, agent=agent)
        created.append(out)
    return {"ok": True, "nodes": created}


def memory_graph(raw: str) -> str:
    """
    memory graph add <label> [kind]
    memory graph link <src> <dst> [rel]
    memory graph query [q]
    memory graph neighbors <label>
    """
    text = (raw or "query").strip()
    parts = text.split()
    if not parts:
        return json.dumps(query(), indent=2)
    cmd = parts[0].lower()
    if cmd == "add" and len(parts) >= 2:
        kind = parts[2] if len(parts) >= 3 else "entity"
        return json.dumps(add_node(parts[1], kind=kind), indent=2)
    if cmd == "link" and len(parts) >= 3:
        rel = parts[3] if len(parts) >= 4 else "related"
        return json.dumps(link(parts[1], parts[2], rel=rel), indent=2)
    if cmd == "query":
        q = " ".join(parts[1:]) if len(parts) > 1 else ""
        return json.dumps(query(q), indent=2)
    if cmd in ("neighbors", "near") and len(parts) >= 2:
        return json.dumps(neighbors(parts[1]), indent=2)
    return json.dumps(
        {
            "ok": False,
            "error": "usage: add <label> [kind] | link <src> <dst> [rel] | query [q] | neighbors <label>",
        },
        indent=2,
    )
