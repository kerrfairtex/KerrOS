"""
memory/session_store.py
=======================
Session-aware chat index (ADR-063).

Extends ADR-058 FTS with session_id / turn indexing, list/browse helpers,
and optional extractive + Soft LLM summaries. Keeps the legacy
sessions_fts table in sync for older callers.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

BASE = Path(os.path.expanduser("~/offline_ai"))
DB_PATH = BASE / "data" / "session_store.db"
MEM_JSON = BASE / "data" / "memory.json"

_lock = threading.RLock()
_current_session_id: Optional[str] = None


def get_current_session_id() -> str:
    global _current_session_id
    with _lock:
        if not _current_session_id:
            _current_session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        return _current_session_id


def start_session(session_id: Optional[str] = None) -> str:
    global _current_session_id
    with _lock:
        _current_session_id = session_id or (
            time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        )
        return _current_session_id


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            started_at TEXT,
            updated_at TEXT,
            title TEXT,
            turn_count INTEGER DEFAULT 0
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            ts TEXT,
            source TEXT
        )
        """
    )
    con.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts
        USING fts5(session_id, role, content, ts, source)
        """
    )
    return con


def index_turn(
    role: str,
    content: str,
    *,
    session_id: Optional[str] = None,
    ts: str = "",
    source: str = "live",
) -> None:
    text = (content or "").strip()
    if not text or role not in ("user", "assistant", "system"):
        return
    sid = session_id or get_current_session_id()
    stamp = ts or time.strftime("%Y-%m-%d %H:%M")
    with _lock:
        con = _conn()
        try:
            row = con.execute(
                "SELECT turn_count FROM sessions WHERE session_id=?", (sid,)
            ).fetchone()
            turn = int(row[0]) + 1 if row else 1
            if row:
                con.execute(
                    "UPDATE sessions SET updated_at=?, turn_count=? WHERE session_id=?",
                    (stamp, turn, sid),
                )
            else:
                title = text[:80].replace("\n", " ")
                con.execute(
                    "INSERT INTO sessions(session_id, started_at, updated_at, title, turn_count) VALUES (?,?,?,?,?)",
                    (sid, stamp, stamp, title, turn),
                )
            con.execute(
                "INSERT INTO turns(session_id, turn, role, content, ts, source) VALUES (?,?,?,?,?,?)",
                (sid, turn, role, text[:8000], stamp, source),
            )
            con.execute(
                "INSERT INTO turns_fts(session_id, role, content, ts, source) VALUES (?,?,?,?,?)",
                (sid, role, text[:8000], stamp, source),
            )
            con.commit()
        finally:
            con.close()
    try:
        from memory.session_fts import index_message

        index_message(role, content, ts=stamp, source=source)
    except Exception:
        pass


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    con = _conn()
    try:
        rows = con.execute(
            """
            SELECT session_id, started_at, updated_at, title, turn_count
            FROM sessions ORDER BY updated_at DESC LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [
            {
                "session_id": r[0],
                "started_at": r[1],
                "updated_at": r[2],
                "title": r[3],
                "turn_count": r[4],
            }
            for r in rows
        ]
    finally:
        con.close()


def browse_session(session_id: str, *, offset: int = 0, limit: int = 30) -> dict[str, Any]:
    sid = (session_id or "").strip()
    con = _conn()
    try:
        meta = con.execute(
            "SELECT session_id, started_at, updated_at, title, turn_count FROM sessions WHERE session_id=?",
            (sid,),
        ).fetchone()
        if not meta:
            return {"ok": False, "error": "session not found"}
        rows = con.execute(
            """
            SELECT turn, role, content, ts FROM turns
            WHERE session_id=? ORDER BY turn ASC LIMIT ? OFFSET ?
            """,
            (sid, max(1, min(int(limit), 200)), max(0, int(offset))),
        ).fetchall()
        return {
            "ok": True,
            "session": {
                "session_id": meta[0],
                "started_at": meta[1],
                "updated_at": meta[2],
                "title": meta[3],
                "turn_count": meta[4],
            },
            "turns": [
                {"turn": r[0], "role": r[1], "content": r[2], "ts": r[3]} for r in rows
            ],
        }
    finally:
        con.close()


def search_sessions(query: str, *, top_k: int = 8) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    con = _conn()
    try:
        safe = q.replace('"', " ").strip()
        fts_q = f'"{safe}"' if " " in safe else safe
        try:
            rows = con.execute(
                """
                SELECT session_id, role, content, ts, bm25(turns_fts) AS score
                FROM turns_fts WHERE turns_fts MATCH ?
                ORDER BY score LIMIT ?
                """,
                (fts_q, max(1, min(int(top_k), 50))),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if rows:
            return [
                {
                    "session_id": r[0],
                    "role": r[1],
                    "content": r[2],
                    "time": r[3],
                    "score": float(r[4]) if r[4] is not None else 0.0,
                }
                for r in rows
            ]
        like = f"%{safe[:80]}%"
        rows = con.execute(
            """
            SELECT session_id, role, content, ts, 0 FROM turns
            WHERE content LIKE ? ORDER BY id DESC LIMIT ?
            """,
            (like, max(1, min(int(top_k), 50))),
        ).fetchall()
        return [
            {"session_id": r[0], "role": r[1], "content": r[2], "time": r[3], "score": 0.0}
            for r in rows
        ]
    finally:
        con.close()


def summarize_hits(hits: list[dict[str, Any]], *, engine: Any = None) -> str:
    """Extractive summary by default; Soft LLM when KERROS_SESSION_LLM_SUMMARY=1."""
    if not hits:
        return "[session] no hits to summarize"
    lines = []
    for h in hits[:6]:
        sid = h.get("session_id") or "?"
        lines.append(f"- [{sid}] {h.get('role')}: {str(h.get('content') or '')[:160]}")
    extractive = "Session recall summary:\n" + "\n".join(lines)
    if str(os.environ.get("KERROS_SESSION_LLM_SUMMARY") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return extractive
    if engine is None:
        return extractive
    try:
        from core.complete import generate_complete

        prompt = (
            "Summarize these past-session excerpts in <=6 bullet points. "
            "No secrets.\n\n" + extractive
        )
        out = generate_complete(engine, prompt, stream=False)
        return str(out or extractive)[:2000]
    except Exception:
        return extractive


def format_session_hits(hits: list[dict[str, Any]], *, limit_chars: int = 1400) -> str:
    if not hits:
        return "[session search] no matches"
    lines = [f"[session search] {len(hits)} hit(s):"]
    used = 0
    for h in hits:
        chunk = (
            f"- ({h.get('session_id')}|{h.get('time')}|{h.get('role')}) "
            f"{str(h.get('content') or '')[:220]}"
        )
        if used + len(chunk) > limit_chars:
            break
        lines.append(chunk)
        used += len(chunk)
    return "\n".join(lines)
