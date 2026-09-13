# Auto-generated wrapper for pipeline_exec.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/pipeline_exec.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("pipeline_exec", "/data/data/com.termux/files/home/offline_ai/tools/pipeline_exec.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/pipeline_exec.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/pipeline_exec.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/pipeline_exec.py\n======================\nPipeline collapsing (ADR-060): run a short Python script that\ncalls allowlisted KerrOS tools via RPC-style helpers, in a subprocess.\n'
