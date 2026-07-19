"""
SUPERVISOR RUNTIME HOOK
=======================

Phase 8.5

Bridge between completion runtime
and supervisor architecture.

Does not replace supervisor modules.

Provides:
- task visibility
- health snapshots
- failure notifications
- recovery signals
"""

from __future__ import annotations

import time


class SupervisorRuntimeHook:


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



    def snapshot(self):

        data = {
            "timestamp": time.time(),
            "tasks": {},
        }


        if self.runtime:

            data["tasks"] = {
                "total":
                    len(self.runtime.tasks),

                "active":
                    len(
                        self.runtime.active_tasks()
                    ),

                "resume":
                    len(
                        self.runtime.resume_candidates()
                    ),
            }


        return data



    def notify_failure(
        self,
        task_id,
        error
    ):

        event = {
            "task_id": task_id,
            "error": str(error),
            "time": time.time(),
        }


        if self.events:

            self.events.publish(
                "supervisor.failure",
                event
            )


        return event



    def health(self):

        snapshot = self.snapshot()

        return {
            "status": "healthy",
            "runtime": snapshot,
        }



hook = SupervisorRuntimeHook()

