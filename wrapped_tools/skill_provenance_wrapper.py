# Auto-generated wrapper for skill_provenance.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/skill_provenance.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("skill_provenance", "/data/data/com.termux/files/home/offline_ai/tools/skill_provenance.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/skill_provenance.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/skill_provenance.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/skill_provenance.py\n=========================\nWrite-origin ContextVar for skill creates (ADR-064).\n\nDistinguishes foreground user-directed writes from background review/auto\nskill creation so curators only auto-manage agent-created skills.\n'
