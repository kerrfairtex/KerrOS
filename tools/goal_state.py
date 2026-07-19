"""
tools/goal_state.py
1) ToolResult — every tool returns this instead of a free-text string,
   so the model (and the loop) has ground truth instead of guessing.
2) GoalState — decomposes a /goal into an ordered step list, persists
   progress to disk, and only advances a step after the previous one's
   ToolResult reports success. Survives restarts/crashes.

Integration:
    from tools.goal_state import ToolResult, GoalState, split_goal_steps

    # in each tool function (fs_tool.py etc), replace ad-hoc strings with:
    return ToolResult(status="ok", tool="make_folder", path=abspath).to_dict()

    # in chat.py, when user sends "/goal ...":
    steps = split_goal_steps(goal_text)
    state = GoalState.start(goal_text, steps)

    # each turn while a goal is active:
    step = state.current_step()
    result = run_tool(step["tool"], step["args"])   # your existing dispatcher
    state.record_result(result)
    if state.is_complete():
        state.clear()
"""

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

STATE_DIR = os.path.expanduser("~/offline_ai/state")
STATE_FILE = os.path.join(STATE_DIR, "goal_state.json")


# ---------------------------------------------------------------------
# 1) Structured tool result — replaces ambiguous strings like "[created] in"
# ---------------------------------------------------------------------

@dataclass
class ToolResult:
    status: str            # "ok" | "fail"
    tool: str               # e.g. "make_folder", "git_clone"
    path: Optional[str] = None    # absolute path acted on, if any
    stdout: str = ""
    stderr: str = ""
    timestamp: float = field(default_factory=time.time)

    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ToolResult":
        return ToolResult(**d)


# ---------------------------------------------------------------------
# 2) Goal decomposition — splits a /goal message into ordered steps.
#    Rule-based first (handles your existing "|"-separated style and
#    common verbs); falls back to a single catch-all step if it can't
#    confidently split, so nothing silently disappears.
# ---------------------------------------------------------------------

_STEP_VERB_RE = re.compile(
    r"\b(make a? ?folder|create a? ?folder|mkdir|clone|add|build|write|"
    r"install|download|move|copy)\b",
    re.IGNORECASE,
)


def split_goal_steps(goal_text: str) -> List[Dict[str, Any]]:
    """
    Returns a list of step dicts: {"desc": str, "tool": None, "args": None,
    "status": "pending"}. tool/args are filled in later by detect_tool()
    per-step, not here — this only decides step BOUNDARIES.
    """
    # Explicit separator the user already uses in /goal messages.
    if "|" in goal_text:
        parts = [p.strip() for p in goal_text.split("|") if p.strip()]
    else:
        # Fall back to splitting on verb boundaries so "make a folder X
        # then clone Y then build now" becomes 3 steps instead of 1.
        matches = list(_STEP_VERB_RE.finditer(goal_text))
        if len(matches) <= 1:
            parts = [goal_text.strip()]
        else:
            parts = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(goal_text)
                parts.append(goal_text[start:end].strip())

    return [
        {"desc": p, "tool": None, "args": None, "status": "pending", "result": None}
        for p in parts
    ]


# ---------------------------------------------------------------------
# 3) Persistent goal state — survives crashes/restarts via disk.
# ---------------------------------------------------------------------

class GoalState:
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    # -- lifecycle -------------------------------------------------
    @staticmethod
    def start(goal_text: str, steps: List[Dict[str, Any]]) -> "GoalState":
        data = {
            "goal_text": goal_text,
            "steps": steps,
            "current_index": 0,
            "created_at": time.time(),
        }
        gs = GoalState(data)
        gs._save()
        return gs

    @staticmethod
    def load() -> Optional["GoalState"]:
        if not os.path.exists(STATE_FILE):
            return None
        with open(STATE_FILE) as f:
            return GoalState(json.load(f))

    def clear(self) -> None:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

    def _save(self) -> None:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    # -- step access -------------------------------------------------
    def current_step(self) -> Optional[Dict[str, Any]]:
        i = self._data["current_index"]
        steps = self._data["steps"]
        return steps[i] if i < len(steps) else None

    def record_result(self, result: ToolResult) -> None:
        i = self._data["current_index"]
        steps = self._data["steps"]
        if i >= len(steps):
            return
        steps[i]["result"] = result.to_dict()
        if result.ok():
            steps[i]["status"] = "done"
            self._data["current_index"] += 1
        else:
            steps[i]["status"] = "failed"
        self._save()

    def is_complete(self) -> bool:
        return self._data["current_index"] >= len(self._data["steps"])

    def is_stuck(self) -> bool:
        step = self.current_step()
        return bool(step and step["status"] == "failed")

    def summary(self) -> str:
        lines = [f"Goal: {self._data['goal_text']}"]
        for i, s in enumerate(self._data["steps"]):
            marker = {"pending": "[ ]", "done": "[x]", "failed": "[!]"}[s["status"]]
            lines.append(f"  {marker} {i+1}. {s['desc']}")
        return "\n".join(lines)


if __name__ == "__main__":
    # Self-test using the exact /goal text from the transcript.
    goal = (
        "Lets build this webapp by using repo from github: "
        "https://github.com/SirDroffilc/Voltizen-Meralco-IDOL-Hackathon | "
        "make a folder in termux home directory named it TOWELCO_TAWI-TAWI "
        "inside it add those repository and other file. build now!"
    )
    steps = split_goal_steps(goal)
    print(f"Decomposed into {len(steps)} step(s):")
    for s in steps:
        print(" -", s["desc"])

    state = GoalState.start(goal, steps)
    print("\n--- initial state ---")
    print(state.summary())

    r1 = ToolResult(status="ok", tool="make_folder", path="/home/TOWELCO_TAWI-TAWI")
    state.record_result(r1)
    print("\n--- after step 1 succeeds ---")
    print(state.summary())
    print("Complete?", state.is_complete())

    state.clear()
    print("\n(state file cleared)")
