"""
COMPLETION RUNTIME API
======================

Phase 8.7

Public interface for the completion architecture.

Agents should eventually call this layer.

It exposes:
- execute()
- health()
- status()

Does not replace existing agents.
"""

from __future__ import annotations

import time


class CompletionRuntimeAPI:


    def __init__(self):

        self.kernel = None

        self._load()



    def _load(self):

        try:
            from core.completion_runtime_kernel import kernel
            self.kernel = kernel

        except Exception:
            self.kernel = None



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

        if not self.kernel:

            raise RuntimeError(
                "Completion kernel unavailable"
            )


        return self.kernel.execute(
            agent=agent,
            engine=engine,
            message=message,
            system=system,
            history=history,
            stream=stream,
            metadata=metadata,
        )



    def health(self):

        return {

            "service":
                "completion_runtime",

            "status":
                "online"
                if self.kernel
                else "offline",

            "time":
                time.time(),

        }



    def status(self):

        return {

            "kernel":
                self.kernel is not None,

            "components":
                {

                "pipeline":
                    bool(
                        getattr(
                            self.kernel,
                            "pipeline",
                            None
                        )
                    ),

                "events":
                    bool(
                        getattr(
                            self.kernel,
                            "events",
                            None
                        )
                    ),

                "authority":
                    bool(
                        getattr(
                            self.kernel,
                            "authority",
                            None
                        )
                    ),

                },

        }



runtime_api = CompletionRuntimeAPI()


def execute(*args, **kwargs):

    return runtime_api.execute(
        *args,
        **kwargs
    )

