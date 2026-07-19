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

        self.orchestrator = None

        self.metrics = {
            "requests": 0,
            "success": 0,
            "failed": 0,
        }

        self._load()


    def _load(self):

        try:
            from core.completion_orchestrator import orchestrator
            self.orchestrator = orchestrator

        except Exception:
            self.orchestrator = None



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


        runtime_metadata = {
            "request_id": request_id,
            "created": started,
        }


        if metadata:
            runtime_metadata.update(metadata)



        try:

            if self.orchestrator:

                result = self.orchestrator.execute(
                    engine=engine,
                    user_message=user_message,
                    system=system,
                    history=history,
                    stream=stream,
                    metadata=runtime_metadata,
                )

            else:

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
            "orchestrator": bool(
                self.orchestrator
            )
        }



runtime = CompletionRuntime()


def run(*args, **kwargs):
    return runtime.run(*args, **kwargs)

