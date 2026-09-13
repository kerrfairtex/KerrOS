# Auto-generated wrapper for registry.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/registry.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("registry", "/data/data/com.termux/files/home/offline_ai/tools/registry.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/registry.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/registry.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/registry.py\n=================\nOpenClaw-style tool registry: JSON schemas + dispatch.\n\nAgents and LLM providers can call list_tools() for function definitions\nand call_tool(name, args) to execute them.\n'
