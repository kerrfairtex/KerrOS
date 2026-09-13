# Auto-generated wrapper for claw_adapter.py
# Original module: /data/data/com.termux/files/home/offline_ai/adapters/tools/claw_adapter.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("claw_adapter", "/data/data/com.termux/files/home/offline_ai/adapters/tools/claw_adapter.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/adapters/tools/claw_adapter.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/adapters/tools/claw_adapter.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\nadapters/tools/claw_adapter.py\n==============================\nClawToolAdapter — ToolPort implementation over OpenClaw-style tools.\n'
