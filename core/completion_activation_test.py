"""
COMPLETION ACTIVATION TEST
==========================

Phase 9.0

End-to-end validation of the
completion architecture.

Safe test only.
"""

from __future__ import annotations

import time



class CompletionActivationTest:


    def __init__(self):

        self.results = {}



    def check(
        self,
        name,
        fn
    ):

        try:

            result = fn()

            self.results[name] = {
                "status": "PASS",
                "result": str(result)[:200],
            }

        except Exception as e:

            self.results[name] = {
                "status": "FAIL",
                "error": str(e),
            }



    def run(self):

        self.results = {}


        self.check(
            "diagnostics",
            lambda:
            __import__(
                "core.completion_diagnostics",
                fromlist=["health"]
            ).health()
        )


        self.check(
            "event_bus",
            lambda:

            __import__(
                "core.completion_event_bus",
                fromlist=["event_bus"]
            ).event_bus.stats()
        )


        self.check(
            "task_runtime",
            lambda:

            __import__(
                "core.persistent_task_runtime",
                fromlist=["runtime"]
            ).runtime.stats()
        )


        self.check(
            "runtime_api",
            lambda:

            __import__(
                "core.completion_runtime_api",
                fromlist=["runtime_api"]
            ).runtime_api.health()
        )


        return {
            "time": time.time(),
            "tests": self.results,
            "passed":
                all(
                    x["status"] == "PASS"
                    for x in self.results.values()
                )
        }



activation_test = CompletionActivationTest()


def run():

    return activation_test.run()

