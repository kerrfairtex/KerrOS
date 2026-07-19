# Tool/Function Design for AI Agents
Each tool should do ONE thing, with a clear name and predictable output format (so detection/parsing logic stays simple).
Dangerous tools (file write, delete, network calls, code execution) need a confirmation gate, especially when acting outside the agent's own sandboxed directory.
Detection-by-regex (intent -> tool mapping) is fragile to phrasing changes — keep patterns narrow and test edge cases, or consider letting the LLM itself choose the tool via structured output for more flexibility.
