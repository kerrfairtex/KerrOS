"""
AGENT CAPABILITY REGISTRY
=========================

Phase 9.2

Registry for agent abilities.

Tracks:
- Skills
- Domains
- Tools
- Metadata

Used by:
- Unified Agent Gateway
- Future Router
- Multi-Agent Consensus
"""

from __future__ import annotations

import time



class AgentCapability:


    def __init__(
        self,
        name,
        skills=None,
        domains=None,
        tools=None,
        metadata=None,
    ):

        self.name = name

        self.skills = skills or []

        self.domains = domains or []

        self.tools = tools or []

        self.metadata = metadata or {}

        self.created = time.time()



    def score(
        self,
        keywords
    ):

        score = 0


        words = set(
            x.lower()
            for x in keywords
        )


        for item in (
            self.skills
            +
            self.domains
            +
            self.tools
        ):

            if item.lower() in words:
                score += 1


        return score



    def info(self):

        return {
            "name": self.name,
            "skills": self.skills,
            "domains": self.domains,
            "tools": self.tools,
            "metadata": self.metadata,
        }




class AgentCapabilityRegistry:


    def __init__(self):

        self.registry = {}



    def register(
        self,
        name,
        skills=None,
        domains=None,
        tools=None,
        metadata=None,
    ):

        agent = AgentCapability(
            name,
            skills,
            domains,
            tools,
            metadata,
        )

        self.registry[name] = agent

        return agent.info()



    def get(
        self,
        name
    ):

        agent = self.registry.get(
            name
        )

        return (
            agent.info()
            if agent
            else None
        )



    def discover(
        self,
        keywords
    ):

        results = []


        for agent in self.registry.values():

            results.append(
                (
                    agent.name,
                    agent.score(
                        keywords
                    )
                )
            )


        return sorted(
            results,
            key=lambda x:x[1],
            reverse=True
        )



    def list(self):

        return {
            name:
            agent.info()

            for name, agent
            in self.registry.items()
        }



registry = AgentCapabilityRegistry()


