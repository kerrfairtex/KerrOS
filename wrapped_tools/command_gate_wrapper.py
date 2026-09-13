# Auto-generated wrapper for command_gate.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/command_gate.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("command_gate", "/data/data/com.termux/files/home/offline_ai/tools/command_gate.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/command_gate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/command_gate.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/command_gate.py\nDrop-in gate: tools only fire on explicit command, never on conversational\nphrasing like "can you help me with that" or "we should probably...".\n'
