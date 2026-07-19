"""
PERSISTENT TASK RUNTIME
=======================

Phase 8.3

Persistent layer for completion tasks.

Responsibilities:
- Save active tasks
- Restore tasks after restart
- Track interrupted execution
- Provide recovery state

Does not replace TaskCompletionManager.
"""

from __future__ import annotations

import os
import json
import time


DEFAULT_PATH = "data/tasks/runtime_tasks.json"



class PersistentTaskRuntime:


    def __init__(
        self,
        path=DEFAULT_PATH
    ):

        self.path = path

        self.tasks = {}

        self._ensure_storage()

        self.load()



    def _ensure_storage(self):

        directory = os.path.dirname(
            self.path
        )

        if directory:
            os.makedirs(
                directory,
                exist_ok=True
            )



    def save(self):

        data = {
            "updated":
                time.time(),

            "tasks":
                self.tasks,
        }


        temp = self.path + ".tmp"


        with open(
            temp,
            "w"
        ) as f:

            json.dump(
                data,
                f,
                indent=2
            )


        os.replace(
            temp,
            self.path
        )



    def load(self):

        if not os.path.exists(
            self.path
        ):

            return


        try:

            with open(
                self.path
            ) as f:

                data = json.load(f)


            self.tasks = data.get(
                "tasks",
                {}
            )


        except Exception:

            self.tasks = {}



    def register(
        self,
        task
    ):

        self.tasks[
            task["id"]
        ] = task

        self.save()



    def update(
        self,
        task_id,
        changes
    ):

        if task_id not in self.tasks:
            return False


        self.tasks[
            task_id
        ].update(
            changes
        )


        self.save()

        return True



    def remove(
        self,
        task_id
    ):

        if task_id in self.tasks:

            del self.tasks[
                task_id
            ]

            self.save()



    def active_tasks(self):

        return [
            t
            for t in self.tasks.values()
            if t.get(
                "status"
            )
            in (
                "running",
                "pending",
                "interrupted"
            )
        ]



    def resume_candidates(self):

        return [
            t
            for t in self.tasks.values()
            if t.get(
                "status"
            ) == "interrupted"
        ]



    def stats(self):

        return {
            "total":
                len(self.tasks),

            "active":
                len(
                    self.active_tasks()
                ),

            "resume":
                len(
                    self.resume_candidates()
                )
        }



runtime = PersistentTaskRuntime()

