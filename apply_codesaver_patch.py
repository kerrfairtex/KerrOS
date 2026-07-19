"""
Run from ~/offline_ai:
    python3 apply_codesaver_patch.py
Patches cli/chat.py. Makes cli/chat.py.bak5 first.
"""
import shutil

PATH = "cli/chat.py"

with open(PATH) as f:
    content = f.read()

anchor_a = (
    '                    saved_files = save_code_blocks(response, folder=folder)\n'
    '                    for f in saved_files:\n'
    '                        print(f"  [saved] {f}")\n'
)
replacement_a = (
    '                    saved_files = save_code_blocks(response, folder=folder)\n'
    '                    _goal_step_ok = True\n'
    '                    for f in saved_files:\n'
    '                        print(f"  [saved] {f}")\n'
)

anchor_b = (
    '                            if result["ok"]:\n'
    '                                print(f"  [fixed] {f} now passes.")\n'
    '                            elif attempts > 0:\n'
    '                                print(f"  [unresolved] {f} still failing after {attempts} attempt(s).")\n'
    '                        else:\n'
    '                            print(f"  [run:skip] {result.get(\'reason\')}")\n'
)
replacement_b = (
    '                            if result["ok"]:\n'
    '                                print(f"  [fixed] {f} now passes.")\n'
    '                            elif attempts > 0:\n'
    '                                print(f"  [unresolved] {f} still failing after {attempts} attempt(s).")\n'
    '                            if not result["ok"]:\n'
    '                                _goal_step_ok = False\n'
    '                        else:\n'
    '                            print(f"  [run:skip] {result.get(\'reason\')}")\n'
)

anchor_c = (
    '                else:\n'
    '                    import os\n'
    '                    for f in saved_files:\n'
    '                        os.remove(f)\n'
    '\n'
    '            # Only save clean short responses\n'
)
replacement_c = (
    '                else:\n'
    '                    import os\n'
    '                    for f in saved_files:\n'
    '                        os.remove(f)\n'
    '\n'
    '                if active_goal and not active_goal.is_complete():\n'
    '                    _step_desc = active_goal.current_step()["desc"]\n'
    '                    if choice == "y":\n'
    '                        active_goal.record_result(ToolResult(\n'
    '                            status="ok" if _goal_step_ok else "fail",\n'
    '                            tool="code_saver",\n'
    '                            path=folder,\n'
    '                            stdout=f"Saved {len(saved_files)} file(s) to {folder}",\n'
    '                        ))\n'
    '                    else:\n'
    '                        active_goal.record_result(ToolResult(\n'
    '                            status="fail",\n'
    '                            tool="code_saver",\n'
    '                            stderr="User declined to save generated code",\n'
    '                        ))\n'
    '                    print(active_goal.summary())\n'
    '                    if active_goal.is_complete():\n'
    '                        print(f"  {GR}[goal] complete!{R}")\n'
    '                        active_goal.clear()\n'
    '                    elif active_goal.is_stuck():\n'
    '                        print(f"  {RE}[goal] still stuck on: {_step_desc}{R}")\n'
    '\n'
    '            # Only save clean short responses\n'
)

for label, anchor in [("A", anchor_a), ("B", anchor_b), ("C", anchor_c)]:
    if anchor not in content:
        raise SystemExit(f"ABORT (anchor {label}): not found — no changes made.\nLooking for:\n{anchor!r}")

shutil.copy(PATH, PATH + ".bak5")
content = content.replace(anchor_a, replacement_a, 1)
content = content.replace(anchor_b, replacement_b, 1)
content = content.replace(anchor_c, replacement_c, 1)
with open(PATH, "w") as f:
    f.write(content)

print(f"Patched {PATH}. Backup at {PATH}.bak5")
print("Now run: python3 -m py_compile cli/chat.py && echo SYNTAX_OK")
