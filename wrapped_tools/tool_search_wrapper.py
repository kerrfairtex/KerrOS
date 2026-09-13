# Auto-generated wrapper for tool_search.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/tool_search.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("tool_search", "/data/data/com.termux/files/home/offline_ai/tools/tool_search.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/tool_search.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/tool_search.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/tool_search.py\n====================\nProgressive tool disclosure (ADR-062).\n\nWhen enabled, large tool catalogs can be hidden behind bridge tools:\n  tool_search / tool_describe / tool_exec_by_name\nCore always-on tools stay eager.\n'
