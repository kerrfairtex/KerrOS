"""
UNIFIED AGENT GATEWAY
====================

Phase 7.2

Controlled completion entry point for all agents.

Purpose:
- Prevent direct engine.generate() dependency
- Attach agent identity
- Attach metadata
- Route through Completion Runtime
- Preserve existing architecture

No agent code replacement required.
Migration can happen gradually.
"""

from __future__ import annotations

import time
import uuid


class UnifiedAgentGateway:

    def __init__(self):

        self.runtime = None

        self.stats = {
            "requests": 0,
            "agents": {},
        }

        self._load_runtime()


    def _load_runtime(self):

        try:
            from core.completion_runtime import runtime
            self.runtime = runtime

        except Exception:
            self.runtime = None



    def complete(
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

        self.stats["requests"] += 1

        self.stats["agents"].setdefault(
            agent,
            0
        )

        self.stats["agents"][agent] += 1


        context = {
            "agent": agent,
            "gateway_request": request_id,
            "timestamp": time.time(),
        }


        if metadata:
            context.update(metadata)



        if self.runtime:

            return self.runtime.run(
                engine=engine,
                user_message=message,
                system=system,
                history=history,
                stream=stream,
                metadata=context,
            )


        # emergency fallback
        return {
            "response": engine.generate(
                message,
                system=system,
                history=history,
                stream=stream,
            ),
            "gateway": "fallback",
        }



    def status(self):

        return {
            "requests": self.stats["requests"],
            "agents": self.stats["agents"],
            "runtime_connected": bool(
                self.runtime
            )
        }



gateway = UnifiedAgentGateway()


def complete(*args, **kwargs):
    return gateway.complete(*args, **kwargs)

