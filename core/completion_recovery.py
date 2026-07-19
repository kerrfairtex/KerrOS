"""
COMPLETION RECOVERY LOOP
========================

Phase 7.5

Recovery controller for completion failures.

Responsibilities:
- Detect failed completion
- Classify failure
- Decide recovery action
- Connect future Retry Controller
- Preserve existing architecture

Does NOT generate responses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RecoveryDecision:

    action: str
    reason: str
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)



class CompletionRecoveryLoop:


    def __init__(self):

        self.history = []

        self.stats = {
            "failures": 0,
            "recoveries": 0,
        }

        self.retry_controller = None

        self._load()



    def _load(self):

        try:
            from core.retry_controller import retry_controller
            self.retry_controller = retry_controller

        except Exception:
            self.retry_controller = None



    def analyze(
        self,
        error=None,
        verification=None,
        response=None,
    ):

        self.stats["failures"] += 1


        reason = "unknown failure"
        action = "retry"
        confidence = 0.5


        if error:

            text = str(error).lower()


            if "timeout" in text:
                reason = "timeout"
                action = "retry"
                confidence = 0.8


            elif "memory" in text:
                reason = "resource failure"
                action = "reduce_context"
                confidence = 0.7


            else:
                reason = "runtime exception"



        elif verification:

            decision = getattr(
                verification,
                "decision",
                None
            )


            if str(decision).lower().endswith(
                "continue"
            ):

                reason = "truncated response"
                action = "continue"
                confidence = 0.9


            elif str(decision).lower().endswith(
                "retry"
            ):

                reason = "quality failure"
                action = "retry"
                confidence = 0.8



        result = RecoveryDecision(
            action=action,
            reason=reason,
            confidence=confidence,
            metadata={
                "time": time.time()
            }
        )


        self.history.append(result)


        return result



    def recoverable(self):

        return (
            self.stats["failures"] > 0
        )



    def status(self):

        return {
            "stats": self.stats,
            "history": len(
                self.history
            ),
            "retry_connected":
                bool(self.retry_controller),
        }



recovery_loop = CompletionRecoveryLoop()


def analyze(*args, **kwargs):
    return recovery_loop.analyze(
        *args,
        **kwargs
    )

