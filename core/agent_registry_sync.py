"""
AGENT REGISTRY SYNC
===================

Phase 9.5 Integration

Connects:
- Agent Discovery
- Capability Registry
- Lifecycle Manager
- Agent Gateway

Does not execute agents.
"""

from __future__ import annotations

import os


class AgentRegistrySync:


    def __init__(self):

        self.discovery = None
        self.registry = None
        self.lifecycle = None
        self.gateway = None

        self._load()



    def _load(self):

        try:
            from core.agent_discovery import discovery
            self.discovery = discovery
        except Exception:
            pass


        try:
            from core.agent_capability_registry import registry
            self.registry = registry
        except Exception:
            pass


        try:
            from core.agent_lifecycle_manager import lifecycle
            self.lifecycle = lifecycle
        except Exception:
            pass


        try:
            from core.agent_gateway import gateway
            self.gateway = gateway
        except Exception:
            pass



    def sync(
        self,
        path="agents"
    ):

        if not self.discovery:
            return []


        self.discovery.scan(path)

        agents = (
            self.discovery.discover_agents()
        )


        synced = []


        for item in agents:

            module = item["module"]

            name = (
                module
                .split(".")[-1]
            )


            metadata = item.get(
                "metadata",
                {}
            )


            skills = metadata.get(
                "skills",
                []
            )

            domains = metadata.get(
                "domains",
                []
            )

            tools = metadata.get(
                "tools",
                []
            )


            if self.registry:

                self.registry.register(
                    name,
                    skills=skills,
                    domains=domains,
                    tools=tools,
                    metadata={
                        "module": module
                    }
                )


            if self.lifecycle:

                self.lifecycle.register(
                    name
                )


            if self.gateway:

                self.gateway.register(
                    name,
                    capabilities=skills
                )


            synced.append(name)


        return synced



sync_manager = AgentRegistrySync()

