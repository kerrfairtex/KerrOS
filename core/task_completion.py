"""
Unified Task Completion Manager
-------------------------------

Purpose
-------
Single source of truth for determining whether a user request has
actually been completed.

This module DOES NOT replace planners, supervisors, recovery systems,
or existing agents.

It only tracks task progress and completion state.

Designed to be safely imported anywhere.

Future phases:
- LLM completion verification
- Evidence scoring
- Multi-agent synchronization
- Persistent resume
"""

from dataclasses import dataclass, field
from typing import Dict, List
from uuid import uuid4
import time


@dataclass
class Checkpoint:
    name: str
    completed: bool = False
    evidence: str = ""


@dataclass
class TaskState:
    id: str
    objective: str
    created: float
    status: str = "running"
    checkpoints: List[Checkpoint] = field(default_factory=list)


class TaskCompletionManager:

    def __init__(self):
        self.tasks: Dict[str, TaskState] = {}

    # --------------------------------------------------------

    def start(self, objective: str):

        task = TaskState(
            id=str(uuid4()),
            objective=objective,
            created=time.time()
        )

        task.checkpoints.append(
            Checkpoint(
                name="Answer objective"
            )
        )

        self.tasks[task.id] = task

        return task

    # --------------------------------------------------------

    def add_checkpoint(self, task_id, name):

        task = self.tasks[task_id]

        task.checkpoints.append(
            Checkpoint(name=name)
        )

    # --------------------------------------------------------

    def complete_checkpoint(
        self,
        task_id,
        checkpoint_name,
        evidence=""
    ):

        task = self.tasks[task_id]

        for cp in task.checkpoints:

            if cp.name == checkpoint_name:

                cp.completed = True
                cp.evidence = evidence
                break

        self._refresh(task)

    # --------------------------------------------------------

    def _refresh(self, task):

        if all(cp.completed for cp in task.checkpoints):
            task.status = "completed"
        else:
            task.status = "running"

    # --------------------------------------------------------

    def remaining(self, task_id):

        task = self.tasks[task_id]

        return [
            cp.name
            for cp in task.checkpoints
            if not cp.completed
        ]

    # --------------------------------------------------------

    def progress(self, task_id):

        task = self.tasks[task_id]

        total = len(task.checkpoints)

        if total == 0:
            return 100.0

        done = sum(
            cp.completed
            for cp in task.checkpoints
        )

        return round(done / total * 100, 2)

    # --------------------------------------------------------

    def is_complete(self, task_id):

        return self.tasks[task_id].status == "completed"

    # --------------------------------------------------------

    def get(self, task_id):

        return self.tasks[task_id]


task_manager = TaskCompletionManager()


# =====================================================================
# POWERHOUSE EXTENSIONS
# Backward-compatible extension layer
# =====================================================================

import json
import os
import threading
from dataclasses import asdict

TASK_STATE_FILE = "data/task_state.json"


class TaskPersistence:

    def __init__(self, manager):
        self.manager = manager
        self.lock = threading.RLock()

        os.makedirs("data", exist_ok=True)

        if os.path.exists(TASK_STATE_FILE):
            self.load()

    def save(self):

        with self.lock:

            payload = {}

            for tid, task in self.manager.tasks.items():

                payload[tid] = {
                    "id": task.id,
                    "objective": task.objective,
                    "created": task.created,
                    "status": task.status,
                    "checkpoints": [
                        asdict(cp)
                        for cp in task.checkpoints
                    ]
                }

            with open(TASK_STATE_FILE, "w") as f:
                json.dump(payload, f, indent=2)

    def load(self):

        with self.lock:

            try:

                with open(TASK_STATE_FILE) as f:
                    raw = json.load(f)

            except Exception:
                return

            self.manager.tasks.clear()

            for tid, item in raw.items():

                t = TaskState(
                    id=item["id"],
                    objective=item["objective"],
                    created=item["created"],
                    status=item["status"]
                )

                for cp in item.get("checkpoints", []):

                    t.checkpoints.append(
                        Checkpoint(
                            name=cp["name"],
                            completed=cp["completed"],
                            evidence=cp.get("evidence", "")
                        )
                    )

                self.manager.tasks[tid] = t


TaskCompletionManager.persistence = property(
    lambda self: getattr(
        self,
        "_persist",
        None
    )
)


_old_init = TaskCompletionManager.__init__


def _new_init(self):

    _old_init(self)

    self.lock = threading.RLock()

    self._persist = TaskPersistence(self)


TaskCompletionManager.__init__ = _new_init


_old_start = TaskCompletionManager.start


def _start(self, objective):

    with self.lock:

        task = _old_start(self, objective)

        self._persist.save()

        return task


TaskCompletionManager.start = _start


_old_add = TaskCompletionManager.add_checkpoint


def _add(self, task_id, name):

    with self.lock:

        _old_add(self, task_id, name)

        self._persist.save()


TaskCompletionManager.add_checkpoint = _add


_old_complete = TaskCompletionManager.complete_checkpoint


def _complete(self, task_id, checkpoint_name, evidence=""):

    with self.lock:

        _old_complete(
            self,
            task_id,
            checkpoint_name,
            evidence
        )

        self._persist.save()


TaskCompletionManager.complete_checkpoint = _complete


def finish(self, task_id):

    with self.lock:

        task = self.tasks[task_id]

        for cp in task.checkpoints:
            cp.completed = True

        task.status = "completed"

        self._persist.save()


TaskCompletionManager.finish = finish


def fail(self, task_id):

    with self.lock:

        self.tasks[task_id].status = "failed"

        self._persist.save()


TaskCompletionManager.fail = fail


def reset(self, task_id):

    with self.lock:

        task = self.tasks[task_id]

        task.status = "running"

        for cp in task.checkpoints:
            cp.completed = False
            cp.evidence = ""

        self._persist.save()


TaskCompletionManager.reset = reset


def delete(self, task_id):

    with self.lock:

        if task_id in self.tasks:
            del self.tasks[task_id]

        self._persist.save()


TaskCompletionManager.delete = delete


def list_tasks(self):

    return list(self.tasks.values())


TaskCompletionManager.list_tasks = list_tasks



# Re-create the singleton AFTER all monkey-patches above are applied.
# The original `task_manager` (line ~154) was built before __init__ was
# patched to add self.lock/_persist, so it was missing both. This fixes
# that instantiation-order bug without touching any of the patch logic.
task_manager = TaskCompletionManager()
