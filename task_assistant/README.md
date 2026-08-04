# Task Assistant

Standalone, single-file (plus SQLite) everyday task assistant.
No CLI complexity to manage, no API keys required to get started —
run it and use the menu.

## The one rule this whole app is built around

The assistant can **draft** anything — plans, messages, suggestions —
at any time, even while you're not around. It can **never execute**
anything in the real world (send a message, post, buy something)
without your explicit approval first. Every draft shows:

- **What** it wants to do
- **Why** (reasoning)
- **Based on what** (evidence / source of truth)

You approve or reject each one. Nothing is hidden, nothing skips the
queue, there is no setting that turns this off.

## Run it

```bash
python3 assistant.py
```

First run creates `assistant.db` (SQLite, local, private — nothing
leaves your device unless a plugin you added explicitly sends it
somewhere, and even then only after your approval).

## How "upgradable" works

Drop a new file in `plugins/` named after an `action_type`
(e.g. `plugins/message.py`) with an `execute(action_dict)` function.
The core app (`assistant.py`) never needs to change to gain new
real-world capabilities — you're only ever adding files, not
rewriting the approval logic. See `plugins/example_message.py`
for the pattern.

## What's intentionally NOT included

- No autonomous sending/posting/purchasing — by design, not a
  missing feature.
- No "trust me" mode. Every real-world action has a human decision
  point, always.
- No hidden rules. `audit_log` records every event the assistant
  ever takes, viewable any time from the menu.

## Extending it further

- Add real schedule/calendar sync: write a plugin that reads/writes
  your actual calendar, triggered from the approval queue like
  everything else.
- Add a smarter planner: replace `suggest_daily_plan()` in
  `assistant.py` with a call to a local or cloud model — the
  approval-queue boundary stays the same regardless of how smart
  the drafting logic gets.
- Version bumps: edit the `VERSION` file the app creates on first run.
