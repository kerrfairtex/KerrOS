"""
cli/command_dispatch.py
=======================
Lightweight command registry — replaces the 62-branch if/elif chain
in cli/chat.py with a dispatch dictionary.

Adding a new command:
1. Write a handler function(handle_user_input, engine, spinner, **ctx) -> bool
2. Register it in COMMANDS dict below
3. Done — no need to touch the if/elif chain
"""

from __future__ import annotations
from typing import Callable, Dict, List, Tuple

# Type: (function, description)
CommandHandler = Callable[..., bool]
COMMANDS: List[Tuple[str, str, CommandHandler]] = []


def register(prefix: str, description: str = ""):
    """Decorator to register a command handler."""
    def decorator(func: CommandHandler) -> CommandHandler:
        COMMANDS.append((prefix, description, func))
        return func
    return decorator


def find_handler(user_input: str):
    """Find the best matching handler for user input.
    
    Prefers exact prefix matches, then falls back to startswith.
    Returns (handler, matched_prefix) or (None, None).
    """
    # Exact match first
    for prefix, desc, handler in COMMANDS:
        if user_input == prefix:
            return handler, prefix
    
    # Then prefix match (longest prefix wins)
    best_match = None
    best_len = 0
    for prefix, desc, handler in COMMANDS:
        if user_input.startswith(prefix) and len(prefix) > best_len:
            best_match = (handler, prefix)
            best_len = len(prefix)
    
    return best_match if best_match else (None, None)


# ── Import all handler registrations ────────────────────────
# This ensures all @register decorators execute at import time
def _import_handlers():
    """Import all modules that register handlers."""
    # Inline handlers are registered below in this file for simplicity
    pass


# ── Built-in handlers ───────────────────────────────────────

@register("/exit", "End session")
def _handle_exit(user, engine, spinner, **ctx):
    from cli.ui import session_end
    session_end()
    return True  # signal to break the loop


@register("/help", "Show help")
def _handle_help(user, engine, spinner, **ctx):
    from cli.ui import divider
    divider()
    cmds = [
        ("/online", "Switch to online mode (Groq)"),
        ("/offline", "Switch to offline mode (local)"),
        ("/mode", "Show current mode"),
        ("/scope", "Show authorized scan/recon targets"),
        ("/scope add <t>", "Authorize a target for active tools"),
        ("/scope remove <t>", "Remove a target from scope"),
        ("/scope arm-deploy", "Arm deploy tools for N minutes"),
        ("/scope policy", "Show declarative scope_policy.yaml"),
        ("/scope policy export", "Regenerate docs/SCOPE_POLICY.md"),
        ("/apistatus", "Show online API health/dead status"),
        ("/integrations", "Adaptive catalog / tiers"),
        ("/setkey groq <key>", "Set Groq API key"),
        ("/switch small|large", "Switch local model"),
        ("/react <task>", "ReAct agent"),
        ("/knowledge <q>", "Knowledge Agent"),
        ("/delegate a:q || b:q2", "Parallel subagents"),
        ("/resume [id|latest]", "Resume indexed session"),
        ("/recall [keyword]", "Search past sessions"),
        ("/clear", "Summarize + clear session"),
        ("/history", "Show conversation history"),
        ("/memory", "Profile + agent memory"),
        ("/tools", "List all tools"),
        ("/read <path>", "Read a workspace file"),
        ("/write <p> :: <txt>", "Write a workspace file"),
        ("/exec <cmd>", "Run shell command"),
        ("/list [path]", "List workspace directory"),
        ("/workspace", "Show claw workspace root"),
        ("/kernel", "Show kernel boot status"),
        ("/health", "Show runtime health report"),
        ("/services", "Show managed service status"),
        ("/events [n]", "Show recent event bus events"),
        ("/schedule", "List/run/cancel jobs"),
        ("/workflows", "List/run/reload workflows"),
        ("/reflect", "Reflection Agent"),
        ("/reflections", "Show reflection lessons"),
        ("/llm", "LLM providers + resilience"),
        ("/capabilities [kind]", "List capabilities"),
        ("/decisions", "Decision log"),
        ("/analyze <topic>", "Deep system analysis"),
        ("/search <query>", "Search knowledge base"),
        ("/learn <text>", "Teach KerrOS"),
        ("/ingest <file>", "Load file into knowledge base"),
        ("/sources", "List RAG sources"),
        ("/exit", "End session"),
    ]
    from cli.ui import BL, GY, R
    for cmd, desc in cmds:
        print(f"  {BL}{cmd:<28}{R} {GY}{desc}{R}")
    divider()
    return False


# ── Dispatch function ───────────────────────────────────────

def dispatch_command(user_input: str, engine, spinner, **ctx) -> bool:
    """Try to dispatch user_input to a registered command handler.
    
    Returns True if the input was handled (caller should continue loop).
    Returns False if no command matched (caller should treat as chat).
    Special case: /exit returns True but sets ctx['should_exit'] = True.
    """
    handler, prefix = find_handler(user_input)
    if handler is None:
        return False  # Not a command, treat as chat
    
    # Call the handler
    result = handler(user_input, engine, spinner, **ctx)
    
    # If handler returns True, check if it's an exit signal
    if result is True and user_input == "/exit":
        ctx['should_exit'] = True
    
    return True
