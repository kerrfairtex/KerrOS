"""
Multi-Agent Completion Consensus
================================

Completion-specific consensus layer.

Purpose:
Combine independent agent completion evaluations.

Architecture:

Agent A
Agent B  ---> Completion Consensus ---> Final Confidence
Agent C


Does NOT replace:
- Supervisor consensus
- Swarm consensus
- Distributed consensus

Only answers:
"Do multiple agents agree this task is complete?"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List
import time


class ConsensusState(Enum):
    ACCEPTED = "accepted"
    REVIEW = "review"
    REJECTED = "rejected"


@dataclass
class AgentEvaluation:

    agent_id: str
    decision: str
    score: float
    evidence: str = ""
    timestamp: float = field(
        default_factory=time.time
    )


@dataclass
class ConsensusResult:

    state: str
    confidence: float
    agreement: float
    participants: int
    reasons: List[str]



class CompletionConsensusEngine:


    ACCEPT_THRESHOLD = 0.75
    REVIEW_THRESHOLD = 0.45


    def __init__(self):

        self.evaluations: Dict[str, List[AgentEvaluation]] = {}



    def add(
        self,
        task_id,
        agent_id,
        decision,
        score,
        evidence=""
    ):

        if task_id not in self.evaluations:
            self.evaluations[task_id] = []


        self.evaluations[task_id].append(
            AgentEvaluation(
                agent_id=agent_id,
                decision=decision,
                score=max(
                    0.0,
                    min(
                        1.0,
                        score
                    )
                ),
                evidence=evidence
            )
        )



    def evaluate(self, task_id):

        agents = self.evaluations.get(
            task_id,
            []
        )


        if not agents:

            return ConsensusResult(
                state="rejected",
                confidence=0.0,
                agreement=0.0,
                participants=0,
                reasons=[
                    "no agent evaluations"
                ]
            )


        confidence = sum(
            a.score
            for a in agents
        ) / len(agents)


        complete_votes = sum(
            1
            for a in agents
            if a.decision == "complete"
        )


        agreement = (
            complete_votes /
            len(agents)
        )


        reasons = []


        if agreement < 0.5:

            reasons.append(
                "agent disagreement"
            )


        if (
            confidence >= self.ACCEPT_THRESHOLD
            and agreement >= 0.66
        ):

            state = "accepted"


        elif confidence >= self.REVIEW_THRESHOLD:

            state = "review"


        else:

            state = "rejected"



        return ConsensusResult(

            state=state,

            confidence=round(
                confidence,
                3
            ),

            agreement=round(
                agreement,
                3
            ),

            participants=len(agents),

            reasons=reasons

        )



    def clear(self, task_id):

        self.evaluations.pop(
            task_id,
            None
        )



completion_consensus = CompletionConsensusEngine()

