"""
memory/profile_store.py
=======================
Durable curated profile memory (ADR-062).

Two file-backed stores under data/memories/:
  MEMORY.md — agent notes / environment facts
  USER.md   — facts about the user

Frozen snapshot at session start for prompt injection; mid-session writes
persist immediately but do not mutate the frozen snapshot until reload.
Entries delimited by §.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

BASE = Path(os.path.expanduser("~/offline_ai"))
MEM_DIR = BASE / "data" / "memories"
ENTRY_DELIMITER = "\n§\n"
MEMORY_CHAR_LIMIT = 2200
USER_CHAR_LIMIT = 1375

_INJECTION = re.compile(
    r"(ignore\s+(?:previous|all|above)\s+instructions|system\s+prompt\s+override|"
    r"disregard\s+(?:your|all)\s+(?:instructions|rules))",
    re.I,
)

_lock = threading.RLock()
_store: Optional["ProfileStore"] = None


def memories_dir() -> Path:
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    return MEM_DIR


class ProfileStore:
    def __init__(self) -> None:
        self.memory_entries: list[str] = []
        self.user_entries: list[str] = []
        self._snapshot = {"memory": "", "user": ""}

    def load(self) -> None:
        d = memories_dir()
        self.memory_entries = self._read(d / "MEMORY.md")
        self.user_entries = self._read(d / "USER.md")
        self._snapshot = {
            "memory": self._render("MEMORY (agent notes)", self._sanitize(self.memory_entries)),
            "user": self._render("USER PROFILE", self._sanitize(self.user_entries)),
        }

    def snapshot_text(self) -> str:
        parts = [v for v in self._snapshot.values() if v.strip()]
        return "\n\n".join(parts)

    def _path(self, target: str) -> Path:
        return memories_dir() / ("USER.md" if target == "user" else "MEMORY.md")

    def _limit(self, target: str) -> int:
        return USER_CHAR_LIMIT if target == "user" else MEMORY_CHAR_LIMIT

    def _entries(self, target: str) -> list[str]:
        return self.user_entries if target == "user" else self.memory_entries

    def _set_entries(self, target: str, entries: list[str]) -> None:
        if target == "user":
            self.user_entries = entries
        else:
            self.memory_entries = entries

    @staticmethod
    def _read(path: Path) -> list[str]:
        if not path.is_file():
            return []
        raw = path.read_text(encoding="utf-8")
        return [e.strip() for e in raw.split(ENTRY_DELIMITER) if e.strip()]

    @staticmethod
    def _write(path: Path, entries: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = ENTRY_DELIMITER.join(entries) if entries else ""
        path.write_text(text + ("\n" if text else ""), encoding="utf-8")

    @staticmethod
    def _sanitize(entries: list[str]) -> list[str]:
        out = []
        for e in entries:
            if _INJECTION.search(e or ""):
                out.append("[BLOCKED: injection pattern — remove via profile_memory]")
            else:
                out.append(e)
        return out

    @staticmethod
    def _render(title: str, entries: list[str]) -> str:
        if not entries:
            return ""
        body = "\n".join(f"- {e}" for e in entries)
        return f"{title}\n{body}"

    def add(self, target: str, content: str) -> dict[str, Any]:
        content = (content or "").strip()
        if not content:
            return {"ok": False, "error": "content required"}
        if _INJECTION.search(content):
            return {"ok": False, "error": "content blocked by safety scan"}
        entries = list(self._entries(target))
        if content in entries:
            return {"ok": True, "note": "already present", "entries": entries}
        trial = entries + [content]
        total = len(ENTRY_DELIMITER.join(trial))
        if total > self._limit(target):
            return {
                "ok": False,
                "error": f"over capacity ({total}/{self._limit(target)}); replace or remove first",
                "entries": entries,
            }
        entries.append(content)
        self._set_entries(target, entries)
        self._write(self._path(target), entries)
        return {"ok": True, "entries": entries, "usage": f"{total}/{self._limit(target)}"}

    def replace(self, target: str, old_text: str, content: str) -> dict[str, Any]:
        old_text = (old_text or "").strip()
        content = (content or "").strip()
        if not old_text or not content:
            return {"ok": False, "error": "old_text and content required"}
        if _INJECTION.search(content):
            return {"ok": False, "error": "content blocked by safety scan"}
        entries = list(self._entries(target))
        matches = [i for i, e in enumerate(entries) if old_text in e]
        if len(matches) != 1:
            return {"ok": False, "error": f"need exactly 1 match for old_text, got {len(matches)}", "entries": entries}
        entries[matches[0]] = content
        total = len(ENTRY_DELIMITER.join(entries))
        if total > self._limit(target):
            return {"ok": False, "error": f"over capacity ({total}/{self._limit(target)})"}
        self._set_entries(target, entries)
        self._write(self._path(target), entries)
        return {"ok": True, "entries": entries}

    def remove(self, target: str, old_text: str) -> dict[str, Any]:
        old_text = (old_text or "").strip()
        entries = list(self._entries(target))
        matches = [i for i, e in enumerate(entries) if old_text in e]
        if len(matches) != 1:
            return {"ok": False, "error": f"need exactly 1 match for old_text, got {len(matches)}", "entries": entries}
        entries.pop(matches[0])
        self._set_entries(target, entries)
        self._write(self._path(target), entries)
        return {"ok": True, "entries": entries}

    def list_entries(self, target: str = "memory") -> dict[str, Any]:
        entries = self._entries(target)
        total = len(ENTRY_DELIMITER.join(entries)) if entries else 0
        return {"ok": True, "target": target, "entries": entries, "usage": f"{total}/{self._limit(target)}"}


def get_profile_store() -> ProfileStore:
    global _store
    with _lock:
        if _store is None:
            _store = ProfileStore()
            _store.load()
        return _store


def profile_memory(action: str, target: str = "memory", content: str = "", old_text: str = "") -> str:
    """Tool entry: action=add|replace|remove|list; target=memory|user."""
    store = get_profile_store()
    target = (target or "memory").strip().lower()
    if target not in ("memory", "user"):
        return json.dumps({"ok": False, "error": "target must be memory|user"})
    action = (action or "").strip().lower()
    with _lock:
        if action == "list":
            out = store.list_entries(target)
        elif action == "add":
            out = store.add(target, content)
        elif action == "replace":
            out = store.replace(target, old_text, content)
        elif action == "remove":
            out = store.remove(target, old_text)
        else:
            out = {"ok": False, "error": "action must be add|replace|remove|list"}
    return json.dumps(out, ensure_ascii=False)
