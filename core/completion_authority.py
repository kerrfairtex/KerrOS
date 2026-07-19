"""
Completion Authority
====================

Final authority for deciding whether an AI task is truly complete.

This module NEVER generates responses.
It ONLY evaluates them.

Decision States
---------------
COMPLETE  -> Objective satisfied.
CONTINUE  -> Continue generation.
RETRY     -> Regenerate response.
FAILED    -> Fatal error / empty response.

Designed to plug into:
- Unified Completion Pipeline
- Task Completion Manager
- Supervisor
- Recovery Engine
- Future LLM verification
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List
import re

try:
    from core.complete import looks_truncated
except Exception:
    def looks_truncated(text):
        return False


class Decision(Enum):
    COMPLETE = "complete"
    CONTINUE = "continue"
    RETRY = "retry"
    FAILED = "failed"


@dataclass
class VerificationResult:
    decision: Decision
    score: float
    reasons: List[str] = field(default_factory=list)
    metrics: Dict = field(default_factory=dict)


class CompletionAuthority:

    MIN_SCORE = 0.70

    PLACEHOLDERS = (
        "todo",
        "coming soon",
        "continue later",
        "fill this",
        "lorem ipsum",
    )

    def verify(self, objective: str, response: str):

        reasons = []
        score = 1.0

        if not response.strip():
            return VerificationResult(
                Decision.FAILED,
                0.0,
                ["empty response"],
            )

        if looks_truncated(response):
            reasons.append("response truncated")
            score -= 0.35

        lower = response.lower()

        for word in self.PLACEHOLDERS:
            if word in lower:
                reasons.append(f"placeholder: {word}")
                score -= 0.20

        if response.count("```") % 2:
            reasons.append("unclosed code block")
            score -= 0.15

        if len(response.split()) < 20:
            reasons.append("response too short")
            score -= 0.20

        objective_words = {
            w for w in re.findall(r"[a-zA-Z]{4,}", objective.lower())
        }

        if objective_words:
            response_words = set(
                re.findall(r"[a-zA-Z]{4,}", lower)
            )

            overlap = len(objective_words & response_words)
            coverage = overlap / max(1, len(objective_words))

            if coverage < 0.20:
                reasons.append("low objective coverage")
                score -= 0.25
        else:
            coverage = 1.0

        score = max(0.0, min(1.0, score))

        if score >= self.MIN_SCORE:
            decision = Decision.COMPLETE
        elif looks_truncated(response):
            decision = Decision.CONTINUE
        elif score >= 0.40:
            decision = Decision.RETRY
        else:
            decision = Decision.FAILED

        return VerificationResult(
            decision=decision,
            score=round(score, 3),
            reasons=reasons,
            metrics={
                "coverage": round(coverage, 3),
                "length": len(response),
                "words": len(response.split()),
            },
        )


completion_authority = CompletionAuthority()

