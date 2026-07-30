"""
runtime/actor_supervision_tree.py
=================================
OTP-style *local* supervision tree foundation (ADR-028).

Thin parent→child registry of ``ActorSupervisor`` instances. Default
strategy: ``one_for_one`` — when a parent actor is marked DEAD, child
supervisors forget observed children (and optionally fire nested hooks).
Not a distributed OTP runtime.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from runtime.actor_supervision import ActorLiveness, ActorSupervisor

Strategy = Literal["one_for_one", "one_for_all"]


@dataclass
class SupervisionTree:
    """Local OTP-inspired tree of ActorSupervisors."""

    strategy: Strategy = "one_for_one"
    _children: dict[str, list[ActorSupervisor]] = field(
        default_factory=dict, init=False, repr=False
    )
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _events: list[dict[str, Any]] = field(default_factory=list, init=False)

    def add_child(self, parent: str, child: ActorSupervisor) -> None:
        key = str(parent or "").strip()
        if not key:
            raise ValueError("parent name required")
        if child is None:
            raise ValueError("child supervisor required")
        with self._lock:
            bucket = self._children.setdefault(key, [])
            if child not in bucket:
                bucket.append(child)

    def remove_child(self, parent: str, child: ActorSupervisor) -> None:
        key = str(parent or "").strip()
        with self._lock:
            bucket = self._children.get(key) or []
            if child in bucket:
                bucket.remove(child)
            if not bucket and key in self._children:
                del self._children[key]

    def children(self, parent: str) -> list[ActorSupervisor]:
        with self._lock:
            return list(self._children.get(str(parent or "").strip()) or [])

    def parents(self) -> list[str]:
        with self._lock:
            return sorted(self._children.keys())

    def wire_parent(self, parent_name: str, supervisor: ActorSupervisor) -> None:
        """
        Wrap ``supervisor.on_dead`` so DEAD for ``parent_name`` triggers tree strategy.
        """
        prev = supervisor.on_dead
        key = str(parent_name or "").strip()

        def _hook(name: str, row: ActorLiveness) -> None:
            if prev is not None:
                try:
                    prev(name, row)
                except Exception:
                    pass
            if str(name or "").strip() == key:
                self.on_parent_dead(key, row)

        supervisor.on_dead = _hook

    def on_parent_dead(self, parent: str, row: ActorLiveness) -> list[str]:
        """
        Apply strategy when ``parent`` is DEAD.

        one_for_one: forget all actors on each child supervisor.
        one_for_all: same for all children under all parents (local cascade).
        """
        affected: list[str] = []
        with self._lock:
            if self.strategy == "one_for_all":
                targets = {
                    p: list(kids) for p, kids in self._children.items()
                }
            else:
                kids = list(self._children.get(str(parent or "").strip()) or [])
                targets = {parent: kids} if kids else {}

        for pname, kids in targets.items():
            for child in kids:
                table = child.table()
                for actor_name in list(table.keys()):
                    child.forget(actor_name)
                    affected.append(f"{pname}/{actor_name}")
                # Nested dead sweep so child hooks can fire if configured.
                try:
                    child.sweep()
                except Exception:
                    pass

        event = {
            "parent": parent,
            "strategy": self.strategy,
            "status": row.status.value if row else "",
            "affected": list(affected),
        }
        with self._lock:
            self._events.append(event)
        return affected

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._events]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "strategy": self.strategy,
                "parents": {
                    p: len(kids) for p, kids in self._children.items()
                },
                "events": len(self._events),
            }


def build_supervision_tree(
    *,
    enabled: bool = False,
    strategy: str = "one_for_one",
) -> Optional[SupervisionTree]:
    if not enabled:
        return None
    strat: Strategy = (
        "one_for_all" if str(strategy).strip().lower() == "one_for_all" else "one_for_one"
    )
    return SupervisionTree(strategy=strat)
