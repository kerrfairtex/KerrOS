"""
UNIFIED AGENT GATEWAY
====================

Phase 9.1

Controlled entry point between
agents and completion runtime.

Responsibilities:
- Agent registration
- Capability tracking
- Request routing
- Runtime connection

Does not replace existing agents.
"""

from __future__ import annotations

import time
import uuid



class AgentRecord:


    def __init__(
        self,
        name,
        capabilities=None
    ):

        self.id = str(uuid.uuid4())

        self.name = name

        self.capabilities = (
            capabilities or []
        )

        self.created = time.time()

        self.requests = 0



    def info(self):

        return {
            "id": self.id,
            "name": self.name,
            "capabilities":
                self.capabilities,
            "requests":
                self.requests,
        }



class UnifiedAgentGateway:


    def __init__(self):

        self.agents = {}

        self.runtime = None
        self.router = None
        self.lifecycle = None

        self._load()



    def _load(self):

        try:

            from core.completion_runtime_api import runtime_api

            self.runtime = runtime_api

        except Exception:

            self.runtime = None


        try:

            from core.agent_router import router

            self.router = router

        except Exception:

            self.router = None


        try:

            from core.agent_lifecycle_manager import lifecycle

            self.lifecycle = lifecycle

        except Exception:

            self.lifecycle = None



    def register(
        self,
        name,
        capabilities=None
    ):

        agent = AgentRecord(
            name,
            capabilities
        )

        self.agents[name] = agent

        if self.lifecycle:

            self.lifecycle.register(
                name
            )

        return agent.info()



    def execute(
        self,
        agent_name,
        engine,
        message,
        system=None,
        history=None,
        stream=False,
        metadata=None,
    ):


        if (
            agent_name in (None, "auto")
            and self.router
        ):

            decision = self.router.route(
                message
            )

            if decision.agent:

                agent_name = decision.agent


        if agent_name not in self.agents:

            self.register(
                agent_name
            )


        agent = self.agents[
            agent_name
        ]


        agent.requests += 1


        if self.lifecycle:

            self.lifecycle.heartbeat(
                agent_name
            )



        if not self.runtime:

            return engine.generate(
                message,
                system=system,
                history=history,
                stream=stream,
            )


        try:

            result = self.runtime.execute(
                agent=agent_name,
                engine=engine,
                message=message,
                system=system,
                history=history,
                stream=stream,
                metadata=metadata,
            )

            if self.lifecycle:

                self.lifecycle.success(
                    agent_name
                )

            return result


        except Exception:

            if self.lifecycle:

                self.lifecycle.failure(
                    agent_name
                )

            raise



    def list_agents(self):

        return {
            name:
            agent.info()

            for name, agent
            in self.agents.items()
        }



gateway = UnifiedAgentGateway()


def execute(*args, **kwargs):

    return gateway.execute(
        *args,
        **kwargs
    )

