"""
COMPLETION CONTROL PLANE
========================

Phase 7.7

Central monitoring interface for the completion system.

Responsibilities:
- System status
- Component health
- Runtime metrics
- Task visibility
- Recovery visibility

Does not execute generation.
"""

from __future__ import annotations

import time


class CompletionControlPlane:


    def __init__(self):

        self.started = time.time()

        self.stack = None
        self.runtime = None
        self.observability = None
        self.recovery = None

        self._load()



    def _load(self):

        try:
            from core.completion_stack import stack
            self.stack = stack
        except Exception:
            pass


        try:
            from core.completion_runtime import runtime
            self.runtime = runtime
        except Exception:
            pass


        try:
            from core.completion_observability import observability
            self.observability = observability
        except Exception:
            pass


        try:
            from core.completion_recovery import recovery_loop
            self.recovery = recovery_loop
        except Exception:
            pass



    def status(self):

        return {

            "uptime":
                round(
                    time.time()
                    - self.started,
                    3
                ),

            "stack":
                self.stack.health()
                if self.stack
                else {},


            "runtime":
                self.runtime.health()
                if self.runtime
                else {},


            "observability":
                self.observability.health()
                if self.observability
                else {},


            "recovery":
                self.recovery.status()
                if self.recovery
                else {},
        }



    def summary(self):

        return {
            "online": True,
            "components":
                len(
                    self.stack.components
                )
                if self.stack
                else 0,
        }



control_plane = CompletionControlPlane()

