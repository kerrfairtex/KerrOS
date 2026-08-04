#!/usr/bin/env python3
"""
Task Assistant — standalone, transparent, draft-and-approve.
=============================================================

CORE PRINCIPLE: The assistant may THINK, PLAN, and DRAFT freely — even
while you're away. It may never SEND, POST, PURCHASE, or COMMIT anything
without your explicit approval. There is no bypass for this. Every
suggestion shows its reasoning and evidence so you can check it, not
just trust it.

Single bundled package: one SQLite file for state, one process to run.
Upgradable via the plugins/ folder and VERSION file — no rebuild needed
for new capabilities, just drop a plugin in.

Run:
    python3 assistant.py
"""
import os
import sys
import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timedelta

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "assistant.db"
VERSION_FILE = APP_DIR / "VERSION"
PLUGINS_DIR = APP_DIR / "plugins"

# ── Version / upgrade tracking ──────────────────────────────────────
def get_version():
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    VERSION_FILE.write_text("1.0.0")
    return "1.0.0"


# ── Storage layer ────────────────────────────────────────────────────
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        status TEXT DEFAULT 'open',      -- open, in_progress, done
        due_date TEXT,
        notes TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS schedule (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        start_time TEXT,
        end_time TEXT,
        notes TEXT,
        created_at TEXT
    );

    -- Anything the assistant wants to DO in the outside world
    -- (send a message, post, buy something, mark a task complete-and-notify)
    -- lands here first. Nothing executes until status = 'approved'.
    CREATE TABLE IF NOT EXISTS approval_queue (
        id TEXT PRIMARY KEY,
        action_type TEXT NOT NULL,       -- message, social_post, purchase, plan, other
        summary TEXT NOT NULL,
        details TEXT,                    -- full content/payload
        reasoning TEXT,                  -- WHY the assistant suggests this
        evidence TEXT,                   -- what facts/data this is based on
        status TEXT DEFAULT 'pending',   -- pending, approved, rejected, executed
        created_at TEXT,
        decided_at TEXT
    );

    -- Full transparent audit trail — every decision point, visible always
    CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        event_type TEXT,
        detail TEXT,
        timestamp TEXT
    );
    """)
    conn.commit()
    conn.close()


def log_event(event_type, detail):
    conn = db()
    conn.execute(
        "INSERT INTO audit_log (id, event_type, detail, timestamp) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), event_type, detail, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ── Task management ──────────────────────────────────────────────────
def add_task(title, due_date=None, notes=None):
    conn = db()
    tid = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT INTO tasks (id, title, due_date, notes, created_at) VALUES (?, ?, ?, ?, ?)",
        (tid, title, due_date, notes, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    log_event("task_created", f"{tid}: {title}")
    return tid


def list_tasks(status=None):
    conn = db()
    if status:
        rows = conn.execute("SELECT * FROM tasks WHERE status=? ORDER BY due_date IS NULL, due_date", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks ORDER BY status, due_date IS NULL, due_date").fetchall()
    conn.close()
    return rows


def complete_task(task_id):
    conn = db()
    conn.execute("UPDATE tasks SET status='done' WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    log_event("task_completed", task_id)


# ── Schedule management ──────────────────────────────────────────────
def add_event(title, start_time, end_time=None, notes=None):
    conn = db()
    eid = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT INTO schedule (id, title, start_time, end_time, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (eid, title, start_time, end_time, notes, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    log_event("event_created", f"{eid}: {title} @ {start_time}")
    return eid


def list_schedule():
    conn = db()
    rows = conn.execute("SELECT * FROM schedule ORDER BY start_time").fetchall()
    conn.close()
    return rows


# ── The approval queue — the actual safety boundary ─────────────────
def propose_action(action_type, summary, details, reasoning, evidence):
    """
    The assistant calls this — NEVER calls anything that acts directly.
    This is the one and only path from 'assistant decided something'
    to 'something happens in the real world', and it always stops here
    until a human approves it.
    """
    conn = db()
    aid = str(uuid.uuid4())[:8]
    conn.execute(
        """INSERT INTO approval_queue
           (id, action_type, summary, details, reasoning, evidence, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (aid, action_type, summary, details, reasoning, evidence, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    log_event("action_proposed", f"{aid}: {summary}")
    return aid


def list_pending():
    conn = db()
    rows = conn.execute("SELECT * FROM approval_queue WHERE status='pending' ORDER BY created_at").fetchall()
    conn.close()
    return rows


def decide(action_id, approve: bool):
    conn = db()
    new_status = "approved" if approve else "rejected"
    conn.execute(
        "UPDATE approval_queue SET status=?, decided_at=? WHERE id=?",
        (new_status, datetime.now().isoformat(), action_id),
    )
    conn.commit()
    conn.close()
    log_event("action_" + new_status, action_id)
    if approve:
        execute_action(action_id)


def execute_action(action_id):
    """
    Only ever called AFTER human approval. This is a stub — wiring a real
    action (send message, post, purchase) means writing a plugin in
    plugins/ that implements the actual send/post/buy call. Nothing here
    executes anything on its own; it just marks the record and hands off
    to a plugin if one is registered for that action_type.
    """
    conn = db()
    row = conn.execute("SELECT * FROM approval_queue WHERE id=?", (action_id,)).fetchone()
    conn.close()
    if not row:
        return
    plugin = load_plugin(row["action_type"])
    if plugin and hasattr(plugin, "execute"):
        plugin.execute(dict(row))
        log_event("action_executed", action_id)
    else:
        log_event("action_approved_no_executor", f"{action_id}: no plugin registered for '{row['action_type']}' — approved but not auto-sent")


# ── Plugin system (this is the 'upgradable' part) ────────────────────
def load_plugin(name):
    """
    Drop a file named plugins/<name>.py with an execute(action_dict)
    function to add a new real-world capability (e.g. plugins/message.py
    to actually send messages via whatever service you use). The core
    app never needs to change — upgrades are additive, not rewrites.
    """
    plugin_path = PLUGINS_DIR / f"{name}.py"
    if not plugin_path.exists():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, plugin_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Planning brain (local Qwen first, OpenRouter fallback) ──────────
def suggest_daily_plan():
    """
    Looks at open tasks + today's schedule, drafts a plan using the
    real planning brain (planner.py). Falls back to a simple rule-based
    draft if both local and cloud models are unavailable — never
    silently does nothing. Always routes through propose_action().
    """
    tasks = list_tasks(status="open")
    events = list_schedule()

    if not tasks and not events:
        return None

    tasks_dicts = [dict(t) for t in tasks]
    events_dicts = [dict(e) for e in events]

    import planner
    draft, reasoning, evidence, source = planner.generate_plan(tasks_dicts, events_dicts)

    if draft is None:
        lines = ["Draft plan for today (rule-based — no model available):"]
        for e in events:
            lines.append(f"  {e['start_time']} — {e['title']}")
        if tasks:
            lines.append("  Open tasks to fit in:")
            for t in tasks[:5]:
                due = f" (due {t['due_date']})" if t["due_date"] else ""
                lines.append(f"    - {t['title']}{due}")
        draft = "\n".join(lines)
        reasoning = "Generated with the rule-based fallback planner (no local or cloud model was reachable)."
        evidence = f"Source: local tasks table ({len(tasks)} rows) + schedule table ({len(events)} rows)."

    summary = f"Daily plan draft ({len(tasks)} open tasks, {len(events)} events)"
    return propose_action(
        action_type="plan",
        summary=summary,
        details=draft,
        reasoning=reasoning,
        evidence=evidence,
    )


def run_specialized_agent(agent_name, task_description):
    """
    Runs one of the 5 specialized agents on a task description.
    Same propose_action() boundary as everything else — the agent
    only ever drafts, never executes.
    """
    import agents
    draft, reasoning, evidence, source = agents.run_agent(agent_name, task_description)
    if draft is None:
        print("No model available (local or cloud) — cannot generate this draft right now.")
        return None

    label = agents.AGENTS[agent_name]["label"]
    return propose_action(
        action_type=f"agent_{agent_name}",
        summary=f"{label} draft: {task_description[:60]}",
        details=draft,
        reasoning=reasoning,
        evidence=evidence,
    )


# ── CLI interface (thin — the app logic above is what matters) ──────
def print_header():
    print(f"\nTask Assistant  v{get_version()}")
    print("Draft-and-approve. Nothing executes without your say.\n")


def main_menu():
    print_header()
    while True:
        print("""
1) Add task
2) List tasks
3) Complete task
4) Add schedule event
5) View schedule
6) Generate daily plan draft
7) Review pending approvals
8) View audit log
9) Ask a specialized agent (Cybersecurity, Data, Web, App, ML)
0) Exit
""")
        choice = input("> ").strip()

        if choice == "1":
            title = input("Task: ").strip()
            due = input("Due date (YYYY-MM-DD, optional): ").strip() or None
            tid = add_task(title, due_date=due)
            print(f"Added task {tid}.")

        elif choice == "2":
            for t in list_tasks():
                due = f" | due {t['due_date']}" if t["due_date"] else ""
                print(f"  [{t['status']}] {t['id']}: {t['title']}{due}")

        elif choice == "3":
            tid = input("Task ID to complete: ").strip()
            complete_task(tid)
            print("Marked done.")

        elif choice == "4":
            title = input("Event: ").strip()
            start = input("Start time (e.g. 2026-08-03 09:00): ").strip()
            end = input("End time (optional): ").strip() or None
            eid = add_event(title, start, end)
            print(f"Added event {eid}.")

        elif choice == "5":
            for e in list_schedule():
                print(f"  {e['start_time']} - {e['title']}")

        elif choice == "6":
            aid = suggest_daily_plan()
            if aid:
                print(f"Draft plan created as pending approval: {aid}")
            else:
                print("Nothing to plan yet — add tasks or events first.")

        elif choice == "7":
            pending = list_pending()
            if not pending:
                print("Nothing pending.")
            for p in pending:
                print(f"\n[{p['id']}] {p['action_type'].upper()}: {p['summary']}")
                print(f"  Reasoning: {p['reasoning']}")
                print(f"  Evidence:  {p['evidence']}")
                print(f"  Details:\n{p['details']}")
                dec = input("  Approve? (y/n/skip): ").strip().lower()
                if dec == "y":
                    decide(p["id"], approve=True)
                    print("  Approved.")
                elif dec == "n":
                    decide(p["id"], approve=False)
                    print("  Rejected.")

        elif choice == "8":
            conn = db()
            rows = conn.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 30").fetchall()
            conn.close()
            for r in rows:
                print(f"  {r['timestamp']}  {r['event_type']}: {r['detail']}")

        elif choice == "9":
            import agents as agents_mod
            print("\nAvailable agents:")
            for key, a in agents_mod.AGENTS.items():
                print(f"  {key}: {a['label']}")
            agent_name = input("Agent key: ").strip()
            if agent_name not in agents_mod.AGENTS:
                print("Unknown agent.")
                continue
            task_desc = input("Describe the task: ").strip()
            aid = run_specialized_agent(agent_name, task_desc)
            if aid:
                print(f"Draft created as pending approval: {aid}")

        elif choice == "0":
            print("Goodbye.")
            break


if __name__ == "__main__":
    init_db()
    try:
        import memory_store
        memory_store.init_readonly_defaults()
    except ImportError:
        pass
    main_menu()
