"""
tools/interrupt.py
==================
Per-thread interrupt signaling for long-running tools (ADR-063).
"""

from __future__ import annotations

import threading

_interrupted_threads: set[int] = set()
_lock = threading.Lock()


def set_interrupt(active: bool, thread_id: int | None = None) -> None:
    tid = thread_id if thread_id is not None else threading.current_thread().ident
    with _lock:
        if active:
            _interrupted_threads.add(tid)
        else:
            _interrupted_threads.discard(tid)


def is_interrupted() -> bool:
    tid = threading.current_thread().ident
    with _lock:
        return tid in _interrupted_threads


def clear_current_thread_interrupt() -> None:
    set_interrupt(False)
