# Auto-generated wrapper for skill_improve.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/skill_improve.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("skill_improve", "/data/data/com.termux/files/home/offline_ai/tools/skill_improve.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/skill_improve.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/skill_improve.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/skill_improve.py\n======================\nSkill self-improve on use (ADR-065).\n\nWhen a skill is viewed, record usage and optionally append a short\n"Lessons" note. Does not auto-rewrite whole skills.\n'
