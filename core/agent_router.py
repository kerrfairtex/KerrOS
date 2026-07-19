"""
INTELLIGENT AGENT ROUTER
========================

Phase 9.3

Selects the best agent for a request.

Uses:
- Agent Capability Registry
- Agent health (future)
- Weighted capability scoring

Does NOT execute agents.
It only decides routing.
"""

from __future__ import annotations

import re
import time



class AgentRouteDecision:


    def __init__(
        self,
        agent=None,
        score=0,
        candidates=None,
        reason=""
    ):

        self.agent = agent
        self.score = score
        self.candidates = candidates or []
        self.reason = reason
        self.time = time.time()



    def to_dict(self):

        return {
            "agent": self.agent,
            "score": self.score,
            "candidates": self.candidates,
            "reason": self.reason,
            "time": self.time,
        }



class IntelligentAgentRouter:


    def __init__(self):

        self.registry = None
        self.lifecycle = None

        self._load()



    def _load(self):

        try:

            from core.agent_capability_registry import registry

            self.registry = registry

        except Exception:

            self.registry = None


        try:

            from core.agent_lifecycle_manager import lifecycle

            self.lifecycle = lifecycle

        except Exception:

            self.lifecycle = None



    def extract_keywords(
        self,
        message
    ):

        words = re.findall(
            r"[a-zA-Z]{3,}",
            message.lower()
        )

        return list(
            set(words)
        )



    def route(
        self,
        message,
        preferred=None,
    ):


        if preferred:

            return AgentRouteDecision(
                agent=preferred,
                score=1.0,
                reason="preferred agent"
            )



        if not self.registry:

            return AgentRouteDecision(
                reason="registry unavailable"
            )



        keywords = self.extract_keywords(
            message
        )


        candidates = self.registry.discover(
            keywords
        )


        if self.lifecycle:

            candidates = [
                c for c in candidates
                if (
                    self.lifecycle.get(c[0])
                    and self.lifecycle.get(c[0])["enabled"]
                    and self.lifecycle.get(c[0])["status"] != "disabled"
                )
            ]


        if not candidates:

            return AgentRouteDecision(
                reason="no candidates"
            )


        best = candidates[0]


        if best[1] <= 0:

            return AgentRouteDecision(
                candidates=candidates,
                reason="no capability match"
            )



        return AgentRouteDecision(
            agent=best[0],
            score=best[1],
            candidates=candidates,
            reason="best capability match"
        )



router = IntelligentAgentRouter()



def route(
    message,
    preferred=None
):

    return router.route(
        message,
        preferred
    )

