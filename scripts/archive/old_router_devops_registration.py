# --- tools/router.py additions ---
# Paste these pieces into your existing router.py at the matching sections.
# Assumes the same structure your other agents (Knowledge, Security, Code, etc.)
# already use for registration + detect_tool() dispatch.

# 1) IMPORT — add near your other agent imports
from tools.devops_agent import DevOpsAgent

# 2) REGISTRY — add to wherever agents are instantiated/keyed
#    (matches the pattern your Knowledge/Security/Code agents already use)
AGENT_REGISTRY = {
    # ... existing entries: "knowledge": KnowledgeAgent(), "security": SecurityAgent(), ...
    "devops": DevOpsAgent(),
}

# 3) EXPLICIT-COMMAND GATE — devops actions must NEVER fire on conversational
#    phrasing. Same rule you enforce for offensive tools: only dispatch on
#    unambiguous imperative commands, not on the agent inferring intent.
DEVOPS_TRIGGER_PHRASES = {
    "deploy now", "deploy to prod", "deploy to production",
    "push to main", "push to github", "create the repo",
    "create repo now", "run migrations", "push migrations",
    "ship it", "go live", "release now",
}

# 4) DETECT_TOOL() — add a branch alongside your existing tool detection
#    (netcat/_calc etc.) so devops intents route to the DevOpsAgent instead
#    of falling through to a generic chat response.
def detect_tool(user_input: str) -> Optional[str]:
    normalized = user_input.strip().lower()

    # ... existing detection branches (nc, _calc, etc.) stay above this ...

    if any(phrase in normalized for phrase in DEVOPS_TRIGGER_PHRASES):
        return "devops"

    # Fallback: let the Planner Agent classify ambiguous build/deploy talk
    # ("can we get this live soon?") as PLANNING, not DEVOPS — planning
    # should draft the spec first, devops should only execute it.
    if any(kw in normalized for kw in ("deploy", "release", "ship", "repo", "migration")):
        return "planner"

    return None


# 5) DISPATCH — add to your main router dispatch function, alongside
#    however you currently invoke agent.run()/agent.act()
def route(user_input: str, context: dict) -> str:
    tool = detect_tool(user_input)

    if tool == "devops":
        agent = AGENT_REGISTRY["devops"]
        # Planner Agent should already have populated context["pipeline_spec"]
        # from an earlier turn (spec-then-execute, never spec-and-execute
        # in one shot for anything gated).
        spec = context.get("pipeline_spec")
        if not spec:
            return ("No build spec found yet — run the Planner Agent first "
                    "to define what gets deployed before I execute anything.")
        result = agent.run_pipeline(spec)
        return format_devops_result(result)   # your existing result-formatting helper

    # ... existing dispatch branches for other tools/agents ...


def format_devops_result(result: dict) -> str:
    """Minimal formatter — replace with your existing CLI-result-to-chat
    formatting if you already have one (e.g. the one used for code_saver.py
    self-correct loop output)."""
    if "halted_at" in result:
        return f"Pipeline stopped: {result['halted_at']}"
    lines = []
    for stage, res in result.items():
        status = "ok" if getattr(res, "ok", False) else "FAILED"
        lines.append(f"{stage}: {status}")
    return "\n".join(lines)
