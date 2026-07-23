"""
COMPLETION SYSTEM DIAGNOSTICS
=============================

Phase 8.9

Unified health inspection for the
completion architecture.

Read-only.
Does not modify runtime state.
"""

from __future__ import annotations

import time


class CompletionDiagnostics:


    def __init__(self):

        self.components = {}

        self.scan()



    def check(
        self,
        name,
        loader
    ):

        try:

            obj = loader()

            self.components[name] = {
                "status": "online",
                "loaded": obj is not None,
            }

        except Exception as e:

            self.components[name] = {
                "status": "offline",
                "error": str(e),
            }



    def scan(self):

        self.components = {}


        self.check(
            "runtime_api",
            lambda:
            __import__(
                "core.completion_runtime_api",
                fromlist=["runtime_api"]
            ).runtime_api
        )


        self.check(
            "coordinator",
            lambda:
            __import__(
                "core.completion_runtime_coordinator",
                fromlist=["coordinator"]
            ).coordinator
        )


        self.check(
            "pipeline",
            lambda:
            __import__(
                "core.unified_completion",
                fromlist=["pipeline"]
            ).pipeline
        )


        self.check(
            "authority",
            lambda:
            __import__(
                "core.completion_authority",
                fromlist=[
                    "completion_authority"
                ]
            ).completion_authority
        )


        self.check(
            "event_bus",
            lambda:
            __import__(
                "core.completion_event_bus",
                fromlist=["event_bus"]
            ).event_bus
        )


        self.check(
            "task_runtime",
            lambda:
            __import__(
                "core.persistent_task_runtime",
                fromlist=["runtime"]
            ).runtime
        )


        self.check(
            "supervisor_hook",
            lambda:
            __import__(
                "core.supervisor_runtime_hook",
                fromlist=["hook"]
            ).hook
        )



    def health(self):

        online = sum(
            1
            for c in self.components.values()
            if c.get("status")
            == "online"
        )


        total = len(
            self.components
        )


        return {

            "timestamp":
                time.time(),

            "healthy":
                online == total,

            "online":
                online,

            "total":
                total,

            "components":
                self.components,

        }



diagnostics = CompletionDiagnostics()


def health():

    diagnostics.scan()

    return diagnostics.health()

