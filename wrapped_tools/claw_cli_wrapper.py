# Auto-generated wrapper for claw_cli.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/claw_cli.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("claw_cli", "/data/data/com.termux/files/home/offline_ai/tools/claw_cli.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/claw_cli.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/claw_cli.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/claw_cli.py\n=================\nCLI integration for OpenClaw-style tools in chat.\n\nParses slash commands and dispatches to tools/registry.py.\n'
