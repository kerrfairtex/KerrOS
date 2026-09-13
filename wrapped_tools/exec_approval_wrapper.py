# Auto-generated wrapper for exec_approval.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/exec_approval.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("exec_approval", "/data/data/com.termux/files/home/offline_ai/tools/exec_approval.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/exec_approval.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/exec_approval.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/exec_approval.py\n======================\nDangerous-command detection for claw exec / bash (ADR-062).\n\nIntegrates as a pre-tool hook. Does not replace scope_gate — runs after it\nfor shell-like tools. Default: deny dangerous patterns unless\nKERROS_EXEC_APPROVE=1 (session allow) or pattern is allowlisted in config.\n'
