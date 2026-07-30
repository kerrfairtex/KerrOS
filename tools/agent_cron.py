"""
tools/agent_cron.py
===================
Router-facing agent cron tool (ADR-062).

Actions: list | create | pause | resume | remove | due
"""

from __future__ import annotations

import json
from typing import Any

from runtime.agent_jobs import (
    create_job,
    due_jobs,
    list_jobs,
    pause_job,
    remove_job,
    resume_job,
)


def agent_cron(action: str, raw: str = "") -> str:
    action = (action or "list").strip().lower()
    parts = [p.strip() for p in (raw or "").split("::")]
    if action in ("list", "ls"):
        jobs = list_jobs()
        if not jobs:
            return "[agent_cron] no jobs"
        lines = ["[agent_cron] jobs:"]
        for j in jobs:
            flag = "paused" if j.get("paused") else "active"
            lines.append(f"- {j['id']} {j['name']} [{flag}] {j['schedule']} — {j['prompt'][:80]}")
        return "\n".join(lines)
    if action == "create":
        # create :: name :: schedule :: prompt
        if len(parts) < 3:
            return "[agent_cron] usage: agent cron create :: <name> :: <m h dom mon dow> :: <prompt>"
        name, schedule, prompt = parts[0], parts[1], "::".join(parts[2:])
        return json.dumps(create_job(name, schedule, prompt), indent=2)
    if action == "pause" and parts:
        return json.dumps(pause_job(parts[0]), indent=2)
    if action == "resume" and parts:
        return json.dumps(resume_job(parts[0]), indent=2)
    if action == "remove" and parts:
        return json.dumps(remove_job(parts[0]), indent=2)
    if action == "due":
        return json.dumps({"ok": True, "due": due_jobs()}, indent=2)
    return "[agent_cron] actions: list|create|pause|resume|remove|due"
