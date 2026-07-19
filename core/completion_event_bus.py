"""
COMPLETION EVENT BUS
====================

Phase 8.1

Internal communication layer.

Purpose:
- Broadcast completion lifecycle events
- Allow supervisor subscriptions
- Allow recovery reactions
- Allow memory logging

Does not execute tasks.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque



class CompletionEvent:


    def __init__(
        self,
        event_type,
        payload=None
    ):

        self.id = str(uuid.uuid4())

        self.type = event_type

        self.payload = payload or {}

        self.timestamp = time.time()



    def to_dict(self):

        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }



class CompletionEventBus:


    def __init__(
        self,
        history_limit=1000
    ):

        self.listeners = defaultdict(list)

        self.history = deque(
            maxlen=history_limit
        )



    def subscribe(
        self,
        event_type,
        callback
    ):

        self.listeners[event_type].append(
            callback
        )



    def publish(
        self,
        event_type,
        payload=None
    ):

        event = CompletionEvent(
            event_type,
            payload
        )


        self.history.append(event)


        for callback in self.listeners.get(
            event_type,
            []
        ):

            try:
                callback(event)

            except Exception:
                pass


        # wildcard listeners

        for callback in self.listeners.get(
            "*",
            []
        ):

            try:
                callback(event)

            except Exception:
                pass


        return event



    def recent(
        self,
        count=20
    ):

        return [
            e.to_dict()
            for e in list(self.history)[-count:]
        ]



    def stats(self):

        return {
            "events":
                len(self.history),

            "listeners":
                sum(
                    len(v)
                    for v in self.listeners.values()
                ),
        }



event_bus = CompletionEventBus()


def publish(*args, **kwargs):
    return event_bus.publish(
        *args,
        **kwargs
    )

