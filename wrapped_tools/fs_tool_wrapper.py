# Auto-generated wrapper for fs_tool.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/fs_tool.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("fs_tool", "/data/data/com.termux/files/home/offline_ai/tools/fs_tool.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/fs_tool.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/fs_tool.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return "\ntools/fs_tool.py\n=================\nDeterministic file/folder operations for KerrOS agents.\n\nWhy this exists: letting the LLM freehand bash for file creation is\nunreliable (missing `mkdir -p`, tree-diagrams mistaken for scripts,\nself-fix loops patching symptoms instead of causes). These functions\nare called directly as tools instead — no shell generation involved.\n\nEvery path is resolved relative to PROJECT_ROOT and cannot escape it\n(basic guardrail against '../../' traversal from a bad model output).\n"
