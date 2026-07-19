"""
Run from ~/offline_ai/cli:
    python3 apply_goal_patch.py
Patches chat.py to wire in GoalState. Makes chat.py.bak2 first.
Idempotent-ish: re-running after a successful patch will fail loudly
(anchor text won't match) instead of double-patching.
"""
import shutil

PATH = "chat.py"
shutil.copy(PATH, "chat.py.bak2")

with open(PATH) as f:
    content = f.read()

# --- Patch 1: import, added right after the router import line -----
anchor1 = "from tools.router import detect_tool, run_tool, detect_domain"
if anchor1 not in content:
    raise SystemExit(f"ABORT: anchor1 not found — no changes made.\nLooking for: {anchor1!r}")
content = content.replace(
    anchor1,
    anchor1 + "\nfrom tools.goal_state import ToolResult, GoalState, split_goal_steps",
    1,
)

# --- Patch 2: goal override before domain/tool detection -----------
anchor2 = (
    '        else:\n'
    '            extract_and_learn(user)\n'
    '            # Save only the raw user text, never tool-augmented content\n'
    '            add_message("user", user)\n'
    '            domain=detect_domain(user)\n'
    '            if domain: print(f"  {PU}◈ Domain: {domain}{R}")\n'
    '\n'
    '            tool_result=None\n'
    '            tool,args=detect_tool(user)\n'
)
if anchor2 not in content:
    raise SystemExit("ABORT: anchor2 not found — no changes made. chat.py may differ from expected.")
replacement2 = (
    '        else:\n'
    '            extract_and_learn(user)\n'
    '            # Save only the raw user text, never tool-augmented content\n'
    '            add_message("user", user)\n'
    '\n'
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
content = content.replace(anchor2, replacement2, 1)

# --- Patch 3: record result + handle no-tool-detected case ---------
anchor3 = (
    '                spinner.stop()\n'
    '                tool_result=run_tool(tool,args)\n'
    '\n'
    '                if tool_result.startswith("__EXPLAIN_REQUEST__"):'
)
if anchor3 not in content:
    raise SystemExit("ABORT: anchor3 not found — no changes made. chat.py may differ from expected.")
replacement3 = (
    '                spinner.stop()\n'
    '                tool_result=run_tool(tool,args)\n'
    '\n'
    '                if active_goal and not active_goal.is_complete():\n'
    '                    _fail_markers = ("error", "fail", "traceback", "not found", "[\u2717]")\n'
    '                    _ok = bool(tool_result) and not any(m in str(tool_result).lower() for m in _fail_markers)\n'
    '                    active_goal.record_result(ToolResult(\n'
    '                        status="ok" if _ok else "fail",\n'
    '                        tool=tool,\n'
    '                        stdout=str(tool_result)[:500],\n'
    '                    ))\n'
    '                    print(active_goal.summary())\n'
    '                    if active_goal.is_complete():\n'
    '                        print(f"  {GR}[goal] complete!{R}")\n'
    '                        active_goal.clear()\n'
    '\n'
    '                if tool_result.startswith("__EXPLAIN_REQUEST__"):'
)
content = content.replace(anchor3, replacement3, 1)

with open(PATH, "w") as f:
    f.write(content)

print("Patched successfully. Backup at chat.py.bak2")
