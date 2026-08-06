"""
memory/scout_defaults.py
========================
Scout inbox agent memory layout + developer-customizable seeds (ADR-106).

Layout under data/agent_memory/stores/scout/:
  notes/user_preference.md
  notes/recurring_contact.md
  email_draft/… (drafts; never auto-send)
  task/complete.md
  task/account_context.md
"""

from __future__ import annotations

from typing import Any

from memory import unified_store as us

USER_PREFERENCE = """# User preference

- Prefer concise replies; bullet points over long paragraphs
- Time zone: Asia/Manila (Barili, Cebu, Philippines)
- Signature: Mahesh
- Never auto-send drafts — always ask before sending
- Daily inbox digest at 08:00
- Treat messages from Robert@, Rodulfo@, Orlando@, Deter@ as high priority
"""

RECURRING_CONTACT = """# Recurring contacts

| Handle / alias | Priority | Notes |
|----------------|----------|-------|
| Robert@        | high     | Always surface in digest |
| Rodulfo@       | high     | Always surface in digest |
| Orlando@       | high     | Always surface in digest |
| Deter@         | high     | Always surface in digest |
"""

ACCOUNT_CONTEXT = """# Account context

- Operator signature: Mahesh
- Locale: Philippines / Barili, Cebu
- Inbox agent: scout (KerrOS default)
- Draft policy: create → review → ask → send (never auto-send)
"""

TASK_COMPLETE = """# Tasks

## Open
- (none yet — agents append completed/open items here)

## Complete
- Seeded Scout memory layout (ADR-106)
"""

ORG_CONVENTIONS = """# Org conventions

- Draft-and-approve always applies — no exceptions.
- Cite evidence for every suggestion.
- Prefer concise output over long explanations.
- Shared learning: what one agent writes to team/, others read on next attach.
"""

ORG_SECURITY = """# Security

- Never auto-send email or external messages.
- Do not exfiltrate secrets from memory files.
- Path traversal outside store roots is forbidden.
"""

ORG_STYLE = """# Style guide

- Bullet points over dense paragraphs.
- Short subject lines for drafts.
- Signature: Mahesh
"""

ORG_ONCALL = """# On-call

- Escalate high-priority contacts immediately in digest.
- Record incident notes under team/ when relevant.
"""

TEAM_DEPLOY = """# Deploy

- Prefer `make` targets for ship; avoid ad-hoc deploy scripts unless documented.
- Record corrections from PRs here with reason + attribution.
"""

TEAM_FLASH = """# Flash tasks

Working scratch for live multi-agent notes. Safe concurrent writes use
content_sha256 preconditions (ADR-106).
"""

TEAM_REPO = """# Repo layout

- KerrOS agent memory: `data/agent_memory/stores/`
- RAG knowledge remains MemoryPort (separate)
- Session transcripts: `memory/session_store.py`
"""


def _seed_file(store: str, rel: str, content: str) -> bool:
    """Write only if missing (do not clobber developer customizations)."""
    existing = us.read(store, rel)
    if existing.get("exists"):
        return False
    us.write(
        store,
        rel,
        content.rstrip() + "\n",
        agent="seed",
        reason="scout_defaults",
        system=True,
    )
    return True


def seed_all() -> dict[str, Any]:
    created = []
    us.register_store(
        "org",
        default_access=us.ACCESS_READ,
        readonly=True,
        description="Org-wide conventions / security / runbooks (read-only)",
    )
    us.register_store(
        "team",
        default_access=us.ACCESS_RW,
        description="Shared team working memory (read/write)",
    )
    us.register_store(
        "scout",
        default_access=us.ACCESS_RW,
        description="Scout inbox agent: prefs, contacts, drafts, tasks",
    )

    seeds = [
        ("org", "conventions.md", ORG_CONVENTIONS),
        ("org", "security.md", ORG_SECURITY),
        ("org", "style-guide.md", ORG_STYLE),
        ("org", "oncall.md", ORG_ONCALL),
        ("team", "deploy.md", TEAM_DEPLOY),
        ("team", "flash_task.md", TEAM_FLASH),
        ("team", "repo_layout.md", TEAM_REPO),
        ("scout", "notes/user_preference.md", USER_PREFERENCE),
        ("scout", "notes/recurring_contact.md", RECURRING_CONTACT),
        ("scout", "task/account_context.md", ACCOUNT_CONTEXT),
        ("scout", "task/complete.md", TASK_COMPLETE),
        (
            "scout",
            "email_draft/README.md",
            "# Email drafts\n\n"
            "Place draft replies here (e.g. `Reply_to_Robert.txt`).\n"
            "Never auto-send — always ask Mahesh before sending.\n",
        ),
    ]
    for store, rel, body in seeds:
        if _seed_file(store, rel, body):
            created.append(f"{store}:{rel}")
    return {"ok": True, "created": created, "stores": [s["name"] for s in us.list_stores()]}
