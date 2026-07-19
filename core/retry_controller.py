"""
Retry Controller
================

Execution controller for completion recovery.

Flow:

CompletionAuthority
        |
        v
CompletionDecisionEngine
        |
        v
RetryController
        |
        +--> retry generation
        +--> continue generation
        +--> stop failure loop


Responsibilities:
- Manage retry attempts
- Manage continuation attempts
- Prevent infinite execution
- Track retry history
- Provide recovery metadata

Does NOT generate responses.
Does NOT replace Supervisor recovery.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Callable
import time


@dataclass
class RetrySession:

    task_id: str

    retries: int = 0
    continuations: int = 0

    history: List[Dict] = field(default_factory=list)

    created: float = field(
        default_factory=time.time
    )


class RetryController:


    MAX_RETRIES = 3
    MAX_CONTINUATIONS = 5


    def __init__(self):

        self.sessions: Dict[str, RetrySession] = {}


    def get_session(self, task_id):

        if task_id not in self.sessions:

            self.sessions[task_id] = RetrySession(
                task_id=task_id
            )

        return self.sessions[task_id]


    def execute(
        self,
        task_id,
        action,
        retry_callback: Callable = None,
        continue_callback: Callable = None,
    ):

        session = self.get_session(task_id)


        result = {
            "task_id": task_id,
            "action": action,
            "executed": False,
        }


        if action == "retry":

            if session.retries >= self.MAX_RETRIES:

                result["reason"] = "retry_limit_reached"
                return result


            session.retries += 1


            if retry_callback:

                result["output"] = retry_callback()
                result["executed"] = True


        elif action == "continue":


            if session.continuations >= self.MAX_CONTINUATIONS:

                result["reason"] = "continuation_limit_reached"
                return result


            session.continuations += 1


            if continue_callback:

                result["output"] = continue_callback()
                result["executed"] = True



        elif action == "complete":

            result["executed"] = True
            result["reason"] = "task_completed"



        else:

            result["reason"] = "failed_action"



        session.history.append(result.copy())


        return result



    def status(self, task_id):

        session = self.sessions.get(task_id)


        if not session:
            return None


        return {

            "task_id": task_id,
            "retries": session.retries,
            "continuations": session.continuations,
            "history": session.history,

        }



retry_controller = RetryController()

