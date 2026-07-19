"""
UNIFIED COMPLETION PIPELINE
===========================

Single authoritative completion pipeline.

Responsibilities
----------------
✓ Create task
✓ Execute generation
✓ Auto continuation
✓ Track progress
✓ Record evidence
✓ Measure execution
✓ Handle failures
✓ Never replace existing architecture

Future extensions plug in here:
    • verifier
    • planner
    • supervisor
    • reflection
    • evaluator
    • memory
    • recovery
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Dict, Optional

from core.complete import generate_complete
from core.task_completion import task_manager


class UnifiedCompletionPipeline:

    def __init__(self):
        self.stats = {
            "requests": 0,
            "completed": 0,
            "failed": 0,
            "total_runtime": 0.0,
        }

    def complete(
        self,
        engine,
        user_message: str,
        system: Optional[str] = None,
        history=None,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:

        self.stats["requests"] += 1

        started = time.time()

        task = task_manager.start(user_message)

        if metadata:
            for k, v in metadata.items():
                setattr(task, k, v)

        try:

            response = generate_complete(
                engine=engine,
                user_message=user_message,
                system=system,
                history=history,
                stream=stream,
            )

            task_manager.complete_checkpoint(
                task.id,
                "Answer objective",
                evidence=response[:1000],
            )

            elapsed = time.time() - started

            self.stats["completed"] += 1
            self.stats["total_runtime"] += elapsed

            task.runtime = elapsed
            task.response_length = len(response)

            return response

        except Exception as e:

            self.stats["failed"] += 1

            task.status = "failed"
            task.error = str(e)
            task.traceback = traceback.format_exc()

            raise

    def metrics(self):

        avg = 0.0

        if self.stats["completed"]:
            avg = (
                self.stats["total_runtime"]
                / self.stats["completed"]
            )

        return {
            **self.stats,
            "average_runtime": round(avg, 3),
            "active_tasks": len(
                [
                    t
                    for t in task_manager.tasks.values()
                    if t.status == "running"
                ]
            ),
        }


pipeline = UnifiedCompletionPipeline()


def complete(*args, **kwargs):
    return pipeline.complete(*args, **kwargs)

