# Agentic Loop Pattern (ReAct-style)
Core loop: Plan -> Act (tool call) -> Observe (result) -> Decide (continue or finish).
Key rule: never trust LLM output as ground truth — verify with execution, tests, or external checks before reporting success.
Common failure mode: infinite loops when the agent doesn't track attempt count. Always cap retries (e.g. max 2-3 attempts) and fall back to asking the user.
State to track per turn: last tool used, last result, attempt count, original goal (to avoid drifting from the task).
