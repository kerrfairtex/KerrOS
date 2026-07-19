"""
COMPLETION ORCHESTRATOR
=======================

Phase 7.0 Integration Layer

Connects:

Agent
 |
Unified Agent Gateway
 |
Unified Completion Pipeline
 |
Task Runtime
 |
Completion Authority
 |
Completion Decision Engine
 |
Retry Controller
 |
Multi-Agent Completion Consensus

This module coordinates existing components.
It does NOT replace them.
"""

from __future__ import annotations

import time
import traceback


class CompletionOrchestrator:

    def __init__(self):

        self.gateway = None
        self.pipeline = None
        self.authority = None
        self.decision_engine = None
        self.retry_controller = None
        self.consensus = None

        self.stats = {
            "requests": 0,
            "completed": 0,
            "failed": 0,
        }

        self._load_components()


    def _load_components(self):

        try:
            from core.unified_agent_gateway import gateway
            self.gateway = gateway
        except Exception:
            pass

        try:
            from core.unified_completion import pipeline
            self.pipeline = pipeline
        except Exception:
            pass

        try:
            from core.completion_authority import completion_authority
            self.authority = completion_authority
        except Exception:
            pass

        try:
            from core.completion_decision import decision_engine
            self.decision_engine = decision_engine
        except Exception:
            pass

        try:
            from core.retry_controller import retry_controller
            self.retry_controller = retry_controller
        except Exception:
            pass

        try:
            from core.completion_consensus import consensus_engine
            self.consensus = consensus_engine
        except Exception:
            pass


    def execute(
        self,
        engine,
        user_message,
        system=None,
        history=None,
        stream=False,
        metadata=None,
    ):

        self.stats["requests"] += 1

        started = time.time()

        try:

            if self.pipeline:

                response = self.pipeline.complete(
                    engine=engine,
                    user_message=user_message,
                    system=system,
                    history=history,
                    stream=stream,
                    metadata=metadata,
                )

            else:

                response = engine.generate(
                    user_message,
                    system=system,
                    history=history,
                    stream=stream,
                )


            verification = None

            if self.authority:

                verification = self.authority.verify(
                    user_message,
                    response
                )


            decision = None

            if self.decision_engine:

                decision = self.decision_engine.evaluate(
                    verification
                )


            self.stats["completed"] += 1


            return {
                "response": response,
                "verification": verification,
                "decision": decision,
                "runtime": round(
                    time.time() - started,
                    3
                ),
            }


        except Exception as e:

            self.stats["failed"] += 1

            return {
                "response": None,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "runtime": round(
                    time.time() - started,
                    3
                ),
            }


    def status(self):

        return {
            **self.stats,
            "components": {
                "gateway": bool(self.gateway),
                "pipeline": bool(self.pipeline),
                "authority": bool(self.authority),
                "decision_engine": bool(self.decision_engine),
                "retry_controller": bool(self.retry_controller),
                "consensus": bool(self.consensus),
            }
        }


orchestrator = CompletionOrchestrator()


def execute(*args, **kwargs):
    return orchestrator.execute(*args, **kwargs)

