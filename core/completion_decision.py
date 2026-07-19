"""
Completion Decision Engine
==========================

Decision layer between:
    CompletionAuthority
            |
            v
    CompletionDecisionEngine
            |
            v
    Pipeline action

Responsibilities:
- Convert verification results into actions
- Apply retry/continuation limits
- Prevent infinite loops
- Track decision history
- Stay independent from existing agents

Does NOT generate responses.
Does NOT replace Supervisor decision engines.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List
import time


class Action(Enum):
    COMPLETE = "complete"
    CONTINUE = "continue"
    RETRY = "retry"
    FAIL = "fail"


@dataclass
class DecisionState:
    task_id: str
    attempts: int = 0
    continuations: int = 0
    history: List[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)


class CompletionDecisionEngine:

    MAX_RETRIES = 3
    MAX_CONTINUATIONS = 5

    def __init__(self):
        self.sessions: Dict[str, DecisionState] = {}


    def register(self, task_id):

        if task_id not in self.sessions:
            self.sessions[task_id] = DecisionState(
                task_id=task_id
            )

        return self.sessions[task_id]


    def decide(self, task_id, verification):

        state = self.register(task_id)

        decision = verification.decision.value


        if decision == "complete":

            action = Action.COMPLETE


        elif decision == "continue":

            if state.continuations >= self.MAX_CONTINUATIONS:
                action = Action.RETRY
            else:
                state.continuations += 1
                action = Action.CONTINUE


        elif decision == "retry":

            if state.attempts >= self.MAX_RETRIES:
                action = Action.FAIL
            else:
                state.attempts += 1
                action = Action.RETRY


        else:

            action = Action.FAIL


        state.history.append(action.value)


        return {
            "action": action.value,
            "attempts": state.attempts,
            "continuations": state.continuations,
            "history": list(state.history),
            "score": verification.score,
            "reasons": verification.reasons,
        }


    def status(self, task_id):

        state = self.sessions.get(task_id)

        if not state:
            return None

        return {
            "task_id": state.task_id,
            "attempts": state.attempts,
            "continuations": state.continuations,
            "history": state.history,
        }


completion_decision_engine = CompletionDecisionEngine()

