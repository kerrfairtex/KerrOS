# Auto-generated wrapper for tool_hooks.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/tool_hooks.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("tool_hooks", "/data/data/com.termux/files/home/offline_ai/tools/tool_hooks.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/tool_hooks.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/tool_hooks.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/tool_hooks.py\n===================\nPre/post tool-call hooks (ADR-056).\n\nDefault: ``scope_gate.check`` is registered as the first pre-hook.\nHooks must not print secrets. Pre-hook exceptions deny the call.\n'
