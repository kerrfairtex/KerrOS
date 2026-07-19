"""
COMPLETION OBSERVABILITY
========================

Phase 7.4

Monitoring layer for the completion architecture.

Tracks:
- requests
- latency
- failures
- decisions
- component health

Does not control execution.
Only observes.
"""

from __future__ import annotations

import time
from collections import deque


class CompletionObservability:


    def __init__(self, history_limit=1000):

        self.events = deque(
            maxlen=history_limit
        )

        self.metrics = {
            "requests": 0,
            "success": 0,
            "failed": 0,
            "total_latency": 0.0,
        }



    def start(self, request_id):

        return {
            "request_id": request_id,
            "start": time.time()
        }



    def record_success(
        self,
        context,
        result=None
    ):

        latency = (
            time.time()
            - context["start"]
        )

        self.metrics["requests"] += 1
        self.metrics["success"] += 1
        self.metrics["total_latency"] += latency


        self.events.append(
            {
                "request_id":
                    context["request_id"],

                "status":
                    "success",

                "latency":
                    round(latency, 4),

                "result":
                    str(result)[:200],

                "time":
                    time.time(),
            }
        )



    def record_failure(
        self,
        context,
        error
    ):

        latency = (
            time.time()
            - context["start"]
        )

        self.metrics["requests"] += 1
        self.metrics["failed"] += 1
        self.metrics["total_latency"] += latency


        self.events.append(
            {
                "request_id":
                    context["request_id"],

                "status":
                    "failed",

                "error":
                    str(error),

                "latency":
                    round(latency,4),

                "time":
                    time.time(),
            }
        )



    def health(self):

        total = self.metrics["requests"]

        avg = 0

        if total:
            avg = (
                self.metrics["total_latency"]
                / total
            )


        return {
            **self.metrics,
            "average_latency":
                round(avg,4),

            "events":
                len(self.events),
        }



    def recent(self, count=10):

        return list(
            self.events
        )[-count:]



observability = CompletionObservability()

