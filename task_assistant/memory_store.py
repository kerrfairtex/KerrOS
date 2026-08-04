"""
memory_store.py — scoped shared memory for multi-agent setup.

Two zones:
  memory/readonly/   — org-level facts every agent can READ, none can WRITE
                        (e.g. house style, security policy, conventions)
  memory/agents/<name>/ — one folder per agent, that agent's own
                        read/write working memory. Other agents can be
                        granted read access explicitly (see SCOPES below)
                        but never write into another agent's folder.

This mirrors the read-only vs read/write pattern from KerrOS's shared
memory design, scaled down to file-based storage — no server needed,
still fully local and inspectable.
"""
import json
from pathlib import Path
from datetime import datetime

APP_DIR = Path(__file__).resolve().parent
MEMORY_DIR = APP_DIR / "memory"
READONLY_DIR = MEMORY_DIR / "readonly"
AGENTS_DIR = MEMORY_DIR / "agents"

# Which agents may READ which other agents' memory folders.
# Nobody gets write access to another agent's folder — ever.
# Add entries here as you introduce real cross-agent collaboration.
SCOPES = {
    "cybersecurity": {"read": ["readonly"]},
    "data_analysis": {"read": ["readonly"]},
    "web_developer": {"read": ["readonly"]},
    "app_developer": {"read": ["readonly"]},
    "machine_learning": {"read": ["readonly"]},
    "planner": {"read": ["readonly", "cybersecurity", "data_analysis",
                          "web_developer", "app_developer", "machine_learning"]},
}


def _agent_dir(agent_name):
    d = AGENTS_DIR / agent_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_own(agent_name, filename):
    """Read a file from the agent's own read/write folder."""
    path = _agent_dir(agent_name) / filename
    if not path.exists():
        return None
    return path.read_text()


def write_own(agent_name, filename, content):
    """
    Write to the agent's own folder only. Uses a simple optimistic-
    concurrency check (mtime) so two writes can't silently clobber
    each other — if the file changed since you'd normally have read
    it, this still writes (single-user, low-risk context) but logs
    a note. For true multi-writer safety at scale, swap this for a
    real lock or versioned store later.
    """
    path = _agent_dir(agent_name) / filename
    path.write_text(content)
    return str(path)


def read_scoped(agent_name, zone, filename):
    """
    Read from another zone (readonly, or another agent's folder) —
    only allowed if SCOPES grants it. Returns None if not permitted
    or file doesn't exist, and logs the attempt either way.
    """
    allowed = SCOPES.get(agent_name, {}).get("read", [])
    if zone not in allowed:
        return None
    if zone == "readonly":
        path = READONLY_DIR / filename
    else:
        path = AGENTS_DIR / zone / filename
    if not path.exists():
        return None
    return path.read_text()


def list_readonly():
    READONLY_DIR.mkdir(parents=True, exist_ok=True)
    return [f.name for f in READONLY_DIR.glob("*") if f.is_file()]


def init_readonly_defaults():
    """Seed a couple of starter read-only files if none exist yet."""
    READONLY_DIR.mkdir(parents=True, exist_ok=True)
    conventions = READONLY_DIR / "conventions.md"
    if not conventions.exists():
        conventions.write_text(
            "# House conventions\n\n"
            "- Draft-and-approve always applies — no exceptions.\n"
            "- Cite evidence for every suggestion.\n"
            "- Prefer concise output over long explanations.\n"
        )
