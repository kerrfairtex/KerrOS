"""
memory/session_fts.py
=====================
SQLite FTS5 index over past chat sessions (ADR-058).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

BASE = Path(os.path.expanduser("~/offline_ai"))
DB_PATH = BASE / "data" / "session_fts.db"
MEM_JSON = BASE / "data" / "memory.json"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
        USING fts5(role, content, ts, source)
        """
    )
    return con


def index_message(role: str, content: str, ts: str = "", source: str = "live") -> None:
    text = (content or "").strip()
    if not text or role not in ("user", "assistant", "system"):
        return
    con = _conn()
    try:
        con.execute(
            "INSERT INTO sessions_fts(role, content, ts, source) VALUES (?,?,?,?)",
            (role, text[:8000], ts or time.strftime("%Y-%m-%d %H:%M"), source),
        )
        con.commit()
    finally:
        con.close()


def reindex_from_memory_json(path: Optional[Path] = None) -> int:
    mem_path = path or MEM_JSON
    if not mem_path.is_file():
        return 0
    try:
        data = json.loads(mem_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(data, list):
        return 0
    con = _conn()
    n = 0
    try:
        con.execute("DELETE FROM sessions_fts")
        for entry in data:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "")
            content = str(entry.get("content") or "").strip()
            if role not in ("user", "assistant") or len(content) < 3:
                continue
            con.execute(
                "INSERT INTO sessions_fts(role, content, ts, source) VALUES (?,?,?,?)",
                (role, content[:8000], str(entry.get("time") or ""), "memory.json"),
            )
            n += 1
        con.commit()
    finally:
        con.close()
    return n


def search_past_sessions(query: str, *, top_k: int = 8) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    con = _conn()
    try:
        count = con.execute("SELECT COUNT(*) FROM sessions_fts").fetchone()[0]
        if count == 0 and MEM_JSON.is_file():
            con.close()
            reindex_from_memory_json()
            con = _conn()
        safe = q.replace('"', " ").strip()
        fts_q = f'"{safe}"' if " " in safe else safe
        try:
            rows = con.execute(
                """
                SELECT role, content, ts, bm25(sessions_fts) AS score
                FROM sessions_fts
                WHERE sessions_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_q, max(1, min(int(top_k), 50))),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        out = [
            {
                "role": r[0],
                "content": r[1],
                "time": r[2],
                "score": float(r[3]) if r[3] is not None else 0.0,
            }
            for r in rows
        ]
        if out:
            return out
        like = f"%{safe[:80]}%"
        rows = con.execute(
            """
            SELECT role, content, ts, 0 FROM sessions_fts
            WHERE content LIKE ?
            ORDER BY rowid DESC LIMIT ?
            """,
            (like, max(1, min(int(top_k), 50))),
        ).fetchall()
        return [
            {"role": r[0], "content": r[1], "time": r[2], "score": 0.0}
            for r in rows
        ]
    except Exception:
        return []
    finally:
        con.close()


def format_search_results(hits: list[dict[str, Any]], *, limit_chars: int = 1200) -> str:
    if not hits:
        return "[session search] no matches"
    lines = [f"[session search] {len(hits)} hit(s):"]
    used = 0
    for h in hits:
        chunk = f"- ({h.get('time')}|{h.get('role')}) {str(h.get('content') or '')[:240]}"
        if used + len(chunk) > limit_chars:
            break
        lines.append(chunk)
        used += len(chunk)
    return "\n".join(lines)
