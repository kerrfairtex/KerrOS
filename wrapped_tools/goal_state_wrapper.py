# Auto-generated wrapper for goal_state.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/goal_state.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("goal_state", "/data/data/com.termux/files/home/offline_ai/tools/goal_state.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/goal_state.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/goal_state.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/goal_state.py\n1) ToolResult — every tool returns this instead of a free-text string,\n   so the model (and the loop) has ground truth instead of guessing.\n2) GoalState — decomposes a /goal into an ordered step list, persists\n   progress to disk, and only advances a step after the previous one\'s\n   ToolResult reports success. Survives restarts/crashes.\n\nIntegration:\n    from tools.goal_state import ToolResult, GoalState, split_goal_steps\n\n    # in each tool function (fs_tool.py etc), replace ad-hoc strings with:\n    return ToolResult(status="ok", tool="make_folder", path=abspath).to_dict()\n\n    # in chat.py, when user sends "/goal ...":\n    steps = split_goal_steps(goal_text)\n    state = GoalState.start(goal_text, steps)\n\n    # each turn while a goal is active:\n    step = state.current_step()\n    result = run_tool(step["tool"], step["args"])   # your existing dispatcher\n    state.record_result(result)\n    if state.is_complete():\n        state.clear()\n'
