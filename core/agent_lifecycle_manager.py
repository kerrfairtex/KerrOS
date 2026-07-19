"""
AGENT LIFECYCLE MANAGER
=======================

Phase 9.4

Manages agent runtime state.

Does not modify agents.

Tracks:
- availability
- health
- version
- activity
- enable/disable state
"""

from __future__ import annotations

import time



class AgentLifecycleRecord:


    def __init__(
        self,
        name,
        version="1.0",
    ):

        self.name = name
        self.version = version

        self.enabled = True
        self.status = "online"

        self.created = time.time()
        self.last_seen = time.time()

        self.requests = 0
        self.failures = 0



    def heartbeat(self):

        self.last_seen = time.time()
        self.status = "online"



    def success(self):

        self.requests += 1
        self.heartbeat()



    def failure(self):

        self.requests += 1
        self.failures += 1
        self.status = "degraded"



    def disable(self):

        self.enabled = False
        self.status = "disabled"



    def enable(self):

        self.enabled = True
        self.status = "online"



    def health_score(self):

        if not self.enabled:
            return 0


        score = 1.0


        if self.failures:
            score -= (
                self.failures /
                max(1, self.requests)
            )


        return max(
            0,
            round(score, 3)
        )



    def info(self):

        return {
            "name": self.name,
            "version": self.version,
            "enabled": self.enabled,
            "status": self.status,
            "requests": self.requests,
            "failures": self.failures,
            "health": self.health_score(),
        }



class AgentLifecycleManager:


    def __init__(self):

        self.agents = {}



    def register(
        self,
        name,
        version="1.0"
    ):

        if name not in self.agents:

            self.agents[name] = (
                AgentLifecycleRecord(
                    name,
                    version
                )
            )

        return self.agents[name].info()



    def heartbeat(
        self,
        name
    ):

        if name in self.agents:

            self.agents[name].heartbeat()



    def success(
        self,
        name
    ):

        if name in self.agents:

            self.agents[name].success()



    def failure(
        self,
        name
    ):

        if name in self.agents:

            self.agents[name].failure()



    def disable(
        self,
        name
    ):

        if name in self.agents:

            self.agents[name].disable()



    def enable(
        self,
        name
    ):

        if name in self.agents:

            self.agents[name].enable()



    def available(self):

        return [
            a.info()
            for a in self.agents.values()
            if a.enabled
            and a.status != "disabled"
        ]



    def get(
        self,
        name
    ):

        agent = self.agents.get(
            name
        )

        return (
            agent.info()
            if agent
            else None
        )



lifecycle = AgentLifecycleManager()

