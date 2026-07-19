"""
COMPLETION ACTIVATION LAYER
===========================

Phase 8.0

Activates the completion architecture.

Responsibilities:
- Unified execution entry
- Connect monitoring
- Connect recovery
- Connect supervisor visibility
- Preserve backward compatibility

Does not replace existing systems.
"""

from __future__ import annotations

import time
import uuid


class CompletionActivation:


    def __init__(self):

        self.gateway = None
        self.observability = None
        self.recovery = None
        self.bridge = None

        self._load()



    def _load(self):

        try:
            from core.unified_agent_gateway import gateway
            self.gateway = gateway
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


        try:
            from core.completion_supervisor_bridge import bridge
            self.bridge = bridge
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


        trace = None

        if self.observability:

            trace = self.observability.start(
                request_id
            )


        try:

            if self.gateway:

                result = self.gateway.complete(
                    agent=agent,
                    engine=engine,
                    message=message,
                    system=system,
                    history=history,
                    stream=stream,
                    metadata=metadata,
                )

            else:

                result = {
                    "response":
                        engine.generate(
                            message,
                            system=system,
                            history=history,
                            stream=stream,
                        )
                }



            if self.observability:

                self.observability.record_success(
                    trace,
                    result,
                )


            if self.bridge:

                self.bridge.snapshot()


            return result



        except Exception as e:


            if self.observability and trace:

                self.observability.record_failure(
                    trace,
                    e,
                )


            if self.recovery:

                recovery = self.recovery.analyze(
                    error=e
                )

            else:

                recovery = None



            return {
                "error": str(e),
                "recovery": recovery,
                "request_id": request_id,
            }



activation = CompletionActivation()


def execute(*args, **kwargs):
    return activation.execute(
        *args,
        **kwargs
    )

