"""
memory/kerros_memory.py
=======================
Tool-facing façade for unified multi-agent memory (ADR-106).
"""

from __future__ import annotations

import json
from typing import Any

from memory import dreaming, manage, unified_store as us


def kerros_memory(raw: str) -> str:
    """
    kerros memory status
    kerros memory bootstrap [session]
    kerros memory attach <store> [read|read_write] [session]
    kerros memory detach <store> [session]
    kerros memory read <store> <path>
    kerros memory write <store> <path> :: <content> [:: sha=<hex>]
    kerros memory files <store>
    kerros memory history <store> <path>
    kerros memory rollback <store> <path> <version>
    kerros memory export|import …
    kerros memory dream [dry|register]
    kerros memory snapshot [session]
    """
    text = (raw or "status").strip()
    low = text.lower()

    if low in ("status", "list"):
        return manage.tool_manage("status")

    if low.startswith("bootstrap"):
        parts = text.split()
        sid = parts[1] if len(parts) > 1 else ""
        return json.dumps(us.bootstrap_session(sid), indent=2)

    if low.startswith("attach "):
        parts = text.split()
        # attach <store> [access] [session]
        store = parts[1] if len(parts) > 1 else ""
        access = us.ACCESS_RW
        sid = us.current_session_id()
        if len(parts) > 2 and parts[2] in (us.ACCESS_READ, us.ACCESS_RW, "ro", "rw"):
            access = us.ACCESS_READ if parts[2] in (us.ACCESS_READ, "ro") else us.ACCESS_RW
            if len(parts) > 3:
                sid = parts[3]
        elif len(parts) > 2:
            sid = parts[2]
        return json.dumps(us.attach(sid, store, access), indent=2)

    if low.startswith("detach "):
        parts = text.split()
        store = parts[1] if len(parts) > 1 else ""
        sid = parts[2] if len(parts) > 2 else us.current_session_id()
        return json.dumps(us.detach(sid, store), indent=2)

    if low.startswith("read "):
        parts = text.split(None, 2)
        if len(parts) < 3:
            return json.dumps({"ok": False, "error": "usage: read <store> <path>"}, indent=2)
        return json.dumps(
            us.read(parts[1], parts[2], session_id=us.current_session_id()),
            indent=2,
        )

    if low.startswith("write "):
        # write <store> <path> :: content [:: sha=...]
        body = text[len("write ") :]
        segs = [s.strip() for s in body.split("::")]
        head = segs[0].split(None, 1)
        if len(head) < 2 or len(segs) < 2:
            return json.dumps(
                {
                    "ok": False,
                    "error": "usage: write <store> <path> :: <content> [:: sha=<hex>]",
                },
                indent=2,
            )
        store, path = head[0], head[1]
        content = segs[1]
        expected = None
        if len(segs) > 2:
            for extra in segs[2:]:
                if extra.lower().startswith("sha="):
                    expected = extra.split("=", 1)[1].strip()
        return json.dumps(
            us.write(
                store,
                path,
                content,
                expected_sha256=expected,
                session_id=us.current_session_id(),
                agent="kerros",
            ),
            indent=2,
        )

    if low.startswith("files "):
        return manage.tool_manage(text)

    if low.startswith("history "):
        return manage.tool_manage(text)

    if low.startswith("rollback "):
        parts = text.split()
        if len(parts) < 4:
            return json.dumps(
                {"ok": False, "error": "usage: rollback <store> <path> <version>"},
                indent=2,
            )
        try:
            ver = int(parts[3])
        except ValueError:
            return json.dumps({"ok": False, "error": "version must be int"}, indent=2)
        return json.dumps(
            us.rollback(
                parts[1],
                parts[2],
                ver,
                session_id=us.current_session_id(),
                agent="kerros",
            ),
            indent=2,
        )

    if low.startswith("export ") or low.startswith("import "):
        return manage.tool_manage(text)

    if low.startswith("dream"):
        arg = text[len("dream") :].strip() or "run"
        return dreaming.tool_dream(arg)

    if low.startswith("snapshot"):
        parts = text.split()
        sid = parts[1] if len(parts) > 1 else us.current_session_id()
        snap = us.snapshot_for_prompt(sid)
        return json.dumps({"ok": True, "session_id": sid, "snapshot": snap}, indent=2)

    if low in ("help", "-h", "--help"):
        return kerros_memory.__doc__ or "kerros memory help"

    return manage.tool_manage(text)
