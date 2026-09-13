# Auto-generated wrapper for safe_math.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/safe_math.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("safe_math", "/data/data/com.termux/files/home/offline_ai/tools/safe_math.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/safe_math.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/safe_math.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/safe_math.py\n==================\nAST-based safe math expression evaluator.\n\nRejects attribute access, names (except allowlisted math constants/functions),\ncomprehensions, calls outside the whitelist, and any other non-arithmetic nodes.\n'
