"""
COMPLETION RUNTIME API
======================

Phase 7.1

Stable public interface for all completion requests.

Responsibilities:
- Single entry point
- Runtime metadata
- Request lifecycle
- Orchestrator connection
- Future distributed execution support

Does NOT replace:
- Agents
- Gateway
- Pipeline
- Supervisor
"""

from __future__ import annotations

import time
import uuid


class CompletionRuntime:

    def __init__(self):

        self.metrics = {
            "requests": 0,
            "success": 0,
            "failed": 0,
        }


    def run(
        self,
        engine,
        user_message,
        system=None,
        history=None,
        stream=False,
        metadata=None,
    ):

        request_id = str(uuid.uuid4())

        started = time.time()

        self.metrics["requests"] += 1


        try:

            result = {
                "response": engine.generate(
                    user_message,
                    system=system,
                    history=history,
                    stream=stream,
                )
            }

            result["request_id"] = request_id
            result["runtime"] = round(
                time.time() - started,
                3
            )


            self.metrics["success"] += 1

            return result


        except Exception as e:

            self.metrics["failed"] += 1

            return {
                "request_id": request_id,
                "error": str(e),
                "runtime": round(
                    time.time() - started,
                    3
                )
            }



    def health(self):

        return {
            "status": "online",
            "metrics": self.metrics,
        }



runtime = CompletionRuntime()


def run(*args, **kwargs):
    return runtime.run(*args, **kwargs)

