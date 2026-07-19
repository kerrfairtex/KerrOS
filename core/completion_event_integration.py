"""
COMPLETION EVENT INTEGRATION
============================

Phase 8.2

Connects completion lifecycle events
to the internal Event Bus.

Events:
- completion.started
- completion.completed
- completion.failed
- completion.recovery

Does not replace execution logic.
"""

from __future__ import annotations


class CompletionEventIntegration:


    def __init__(self):

        self.bus = None

        self._load()



    def _load(self):

        try:
            from core.completion_event_bus import event_bus
            self.bus = event_bus

        except Exception:
            self.bus = None



    def started(
        self,
        request_id,
        agent,
        message,
    ):

        if not self.bus:
            return

        self.bus.publish(
            "completion.started",
            {
                "request_id": request_id,
                "agent": agent,
                "message": message[:200],
            }
        )



    def completed(
        self,
        request_id,
        result,
    ):

        if not self.bus:
            return

        self.bus.publish(
            "completion.completed",
            {
                "request_id": request_id,
                "response_size":
                    len(
                        str(result)
                    ),
            }
        )



    def failed(
        self,
        request_id,
        error,
    ):

        if not self.bus:
            return

        self.bus.publish(
            "completion.failed",
            {
                "request_id": request_id,
                "error": str(error),
            }
        )



    def recovery(
        self,
        request_id,
        decision,
    ):

        if not self.bus:
            return

        self.bus.publish(
            "completion.recovery",
            {
                "request_id": request_id,
                "decision":
                    str(decision),
            }
        )



integration = CompletionEventIntegration()

