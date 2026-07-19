"""
DYNAMIC AGENT DISCOVERY
=======================

Phase 9.5

Automatically discovers agents
inside the project.

Does not execute agents.
Only finds and registers them.
"""

from __future__ import annotations

import os
import importlib
import time



class AgentDiscovery:


    def __init__(self):

        self.discovered = {}



    def scan(
        self,
        path="agents"
    ):

        found = {}


        if not os.path.exists(path):

            return found


        for root, dirs, files in os.walk(path):

            for file in files:

                if (
                    file.endswith(".py")
                    and not file.startswith("_")
                ):

                    module = (
                        root
                        .replace("/", ".")
                        + "."
                        + file[:-3]
                    )


                    found[module] = {
                        "module": module,
                        "file": os.path.join(
                            root,
                            file
                        ),
                        "time": time.time(),
                    }


        self.discovered = found

        return found



    def load_metadata(
        self,
        module
    ):

        # SAFE MODE:
        # Never import agent modules during discovery.
        # Importing may start daemons or runtimes.

        return {}



    def discover_agents(self):

        results = []


        for module, data in self.discovered.items():

            metadata = self.load_metadata(
                module
            )

            results.append(
                {
                    **data,
                    "metadata": metadata,
                }
            )


        return results



discovery = AgentDiscovery()

