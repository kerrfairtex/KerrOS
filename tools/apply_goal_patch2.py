"""
Run from ~/offline_ai (the parent dir, not cli/ or tools/):
    python3 apply_goal_patch2.py
Patches tools/router.py and cli/chat.py. Makes .bak3 copies of both first.
Aborts with NO changes to a file if that file's anchor text doesn't match
exactly — safe to re-run after fixing an anchor by hand.
"""
import shutil

def patch_file(path, anchor, replacement, label):
    with open(path) as f:
        content = f.read()
    if anchor not in content:
        raise SystemExit(f"ABORT ({label}): anchor not found in {path} — no changes made.\nLooking for:\n{anchor!r}")
    shutil.copy(path, path + ".bak3")
    content = content.replace(anchor, replacement, 1)
    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {path} ({label}). Backup at {path}.bak3")


# --- router.py: allow goal steps to bypass the explicit-command gate ---
router_anchor = (
    "def detect_tool(text):\n"
    "    if not is_explicit_command(text):\n"
    "        return (None, None)\n"
)
router_replacement = (
    "def detect_tool(text, bypass_gate=False):\n"
    "    if not bypass_gate and not is_explicit_command(text):\n"
    "        return (None, None)\n"
)
patch_file("tools/router.py", router_anchor, router_replacement, "gate bypass param")


# --- chat.py: mark _is_goal_step, pass bypass_gate, handle no-tool-match ---
chat_anchor_a = (
    '            active_goal = GoalState.load()\n'
    '            if user.strip().lower().startswith("/goal "):\n'
    '                goal_text = user[6:].strip()\n'
    '                steps = split_goal_steps(goal_text)\n'
    '                active_goal = GoalState.start(goal_text, steps)\n'
    '                print(f"  {GO}[goal] started — {len(steps)} step(s){R}")\n'
    '                print(active_goal.summary())\n'
    '                user = active_goal.current_step()["desc"]\n'
    '            elif active_goal and not active_goal.is_complete():\n'
    '                if active_goal.is_stuck():\n'
    '                    print(f"  {RE}[goal] stuck on: {active_goal.current_step()[\'desc\']}{R}")\n'
    '                    print(active_goal.summary())\n'
    '                    active_goal.clear()\n'
    '                    active_goal = None\n'
    '                else:\n'
    '                    user = active_goal.current_step()["desc"]\n'
    '\n'
    '            domain=detect_domain(user)\n'
    '            if domain: print(f"  {PU}◈ Domain: {domain}{R}")\n'
    '\n'
    '            tool_result=None\n'
    '            tool,args=detect_tool(user)\n'
)
chat_replacement_a = (
    '            active_goal = GoalState.load()\n'
    '            _is_goal_step = False\n'
    '            if user.strip().lower().startswith("/goal "):\n'
    '                goal_text = user[6:].strip()\n'
    '                steps = split_goal_steps(goal_text)\n'
    '                active_goal = GoalState.start(goal_text, steps)\n'
    '                print(f"  {GO}[goal] started — {len(steps)} step(s){R}")\n'
    '                print(active_goal.summary())\n'
    '                user = active_goal.current_step()["desc"]\n'
    '                _is_goal_step = True\n'
    '            elif active_goal and not active_goal.is_complete():\n'
    '                if active_goal.is_stuck():\n'
    '                    print(f"  {RE}[goal] stuck on: {active_goal.current_step()[\'desc\']}{R}")\n'
    '                    print(active_goal.summary())\n'
    '                    active_goal.clear()\n'
    '                    active_goal = None\n'
    '                else:\n'
    '                    user = active_goal.current_step()["desc"]\n'
    '                    _is_goal_step = True\n'
    '\n'
    '            domain=detect_domain(user)\n'
    '            if domain: print(f"  {PU}◈ Domain: {domain}{R}")\n'
    '\n'
    '            tool_result=None\n'
    '            tool,args=detect_tool(user, bypass_gate=_is_goal_step)\n'
)

chat_anchor_b = (
    '                else:\n'
    '                    divider()\n'
    '                    for line in tool_result.split("\\n"):\n'
    '                        print(f"  {GY}{line}{R}")\n'
    '                    divider()\n'
    '\n'
    '            from prompts.system import SYSTEM_PROMPT\n'
)
chat_replacement_b = (
    '                else:\n'
    '                    divider()\n'
    '                    for line in tool_result.split("\\n"):\n'
    '                        print(f"  {GY}{line}{R}")\n'
    '                    divider()\n'
    '\n'
    '            elif active_goal and not active_goal.is_complete():\n'
    '                _stuck_desc = active_goal.current_step()["desc"]\n'
    '                active_goal.record_result(ToolResult(\n'
    '                    status="fail",\n'
    '                    tool="none",\n'
    '                    stderr=f"No tool matched for step: {_stuck_desc}",\n'
    '                ))\n'
    '                print(f"  {RE}[goal] stuck — no tool matched for: {_stuck_desc}{R}")\n'
    '                print(active_goal.summary())\n'
    '\n'
    '            from prompts.system import SYSTEM_PROMPT\n'
)

with open("cli/chat.py") as f:
    chat_content = f.read()
if chat_anchor_a not in chat_content:
    raise SystemExit(f"ABORT (chat.py part A): anchor not found — no changes made.")
if chat_anchor_b not in chat_content:
    raise SystemExit(f"ABORT (chat.py part B): anchor not found — no changes made.")

shutil.copy("cli/chat.py", "cli/chat.py.bak3")
chat_content = chat_content.replace(chat_anchor_a, chat_replacement_a, 1)
chat_content = chat_content.replace(chat_anchor_b, chat_replacement_b, 1)
with open("cli/chat.py", "w") as f:
    f.write(chat_content)
print("Patched cli/chat.py (goal-step bypass + stuck-on-no-tool). Backup at cli/chat.py.bak3")

print("\nDone. Now run:\n  python3 -m py_compile tools/router.py cli/chat.py && echo SYNTAX_OK")
