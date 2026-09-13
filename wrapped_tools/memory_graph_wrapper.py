# Auto-generated wrapper for memory_graph.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/memory_graph.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("memory_graph", "/data/data/com.termux/files/home/offline_ai/tools/memory_graph.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/memory_graph.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/memory_graph.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/memory_graph.py\n=====================\nMemory graph tool (ADR-106) — entities + relations for agent memory.\n\nComplements bash (shell) so KerrOS remembers structured links across agents.\nFile-backed at data/agent_memory/graph.json.\n'
