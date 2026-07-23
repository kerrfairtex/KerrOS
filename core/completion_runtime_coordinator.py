"""
COMPLETION RUNTIME COORDINATOR
==============================

Phase 8.6 — renamed from CompletionRuntimeKernel (KOS-015).

Central coordination layer for the completion pipeline. This is userspace
orchestration, NOT the KerrOS system kernel in kernel/.

Connects:
- Unified Agent Gateway
- Unified Completion Pipeline
- Completion Authority
- Decision Engine
- Retry Controller
- Consensus
- Persistence
- Event System
- Supervisor Hook
"""

from __future__ import annotations

import time
import uuid


class CompletionRuntimeCoordinator:
    def __init__(self):
        self.pipeline = None
        self.authority = None
        self.events = None
        self.sync = None
        self.supervisor = None
        self._load()

    def _load(self):
        try:
            from core.unified_completion import pipeline
            self.pipeline = pipeline
        except Exception:
            pass

        try:
            from core.completion_authority import completion_authority
            self.authority = completion_authority
        except Exception:
            pass

        try:
            from core.completion_event_bus import event_bus
            self.events = event_bus
        except Exception:
            pass

        try:
            from core.runtime_synchronizer import synchronizer
            self.sync = synchronizer
        except Exception:
            pass

        try:
            from core.supervisor_runtime_hook import hook
            self.supervisor = hook
        except Exception:
            pass

    def execute(
        self,
        agent,
        engine,
        message,
        system=None,
        history=None,
        stream=False,
        metadata=None,
    ):
        request_id = str(uuid.uuid4())
        started = time.time()

        if self.events:
            self.events.publish(
                "runtime.started",
                {"id": request_id, "agent": str(agent)},
            )

        try:
            result = self.pipeline.complete(
                engine=engine,
                user_message=message,
                system=system,
                history=history,
                stream=stream,
                metadata=metadata,
            )

            verification = None
            if self.authority:
                verification = self.authority.verify(message, result)

            elapsed = time.time() - started
            output = {
                "request_id": request_id,
                "response": result,
                "verification": verification,
                "runtime": round(elapsed, 4),
            }

            if self.events:
                self.events.publish("runtime.completed", output)

            return output

        except Exception as e:
            if self.events:
                self.events.publish(
                    "runtime.failed",
                    {"id": request_id, "error": str(e)},
                )
            raise


coordinator = CompletionRuntimeCoordinator()


def execute(*args, **kwargs):
    return coordinator.execute(*args, **kwargs)
