"""
RUNTIME SYNCHRONIZER
====================

Phase 8.4

Connects completion lifecycle state
with persistent storage and events.

Responsibilities:
- Register tasks
- Update task state
- Publish lifecycle events
- Preserve crash recovery state

Does not replace:
- TaskCompletionManager
- CompletionPipeline
- Supervisor
"""

from __future__ import annotations

import time



class RuntimeSynchronizer:


    def __init__(self):

        self.runtime = None
        self.events = None

        self._load()



    def _load(self):

        try:
            from core.persistent_task_runtime import runtime
            self.runtime = runtime
        except Exception:
            pass


        try:
            from core.completion_event_bus import event_bus
            self.events = event_bus
        except Exception:
            pass



    def register_task(
        self,
        task
    ):

        data = {
            "id": task.id,
            "objective": task.objective,
            "status": task.status,
            "created": task.created,
            "updated": time.time(),
        }


        if self.runtime:
            self.runtime.register(data)


        if self.events:

            self.events.publish(
                "task.registered",
                data
            )


        return data



    def update_task(
        self,
        task_id,
        status,
        metadata=None
    ):

        update = {
            "status": status,
            "updated": time.time(),
        }


        if metadata:
            update.update(metadata)


        if self.runtime:

            self.runtime.update(
                task_id,
                update
            )


        if self.events:

            self.events.publish(
                "task.updated",
                {
                    "id": task_id,
                    **update
                }
            )


        return update



    def completed(
        self,
        task_id,
        evidence=None
    ):

        return self.update_task(
            task_id,
            "completed",
            {
                "evidence": evidence or ""
            }
        )



    def failed(
        self,
        task_id,
        error
    ):

        return self.update_task(
            task_id,
            "failed",
            {
                "error": str(error)
            }
        )



    def interrupted(
        self,
        task_id
    ):

        return self.update_task(
            task_id,
            "interrupted"
        )



synchronizer = RuntimeSynchronizer()

