# Auto-generated wrapper for agent_cron.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/agent_cron.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("agent_cron", "/data/data/com.termux/files/home/offline_ai/tools/agent_cron.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/agent_cron.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/agent_cron.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/agent_cron.py\n===================\nRouter-facing agent cron tool (ADR-062).\n\nActions: list | create | pause | resume | remove | due\n'
