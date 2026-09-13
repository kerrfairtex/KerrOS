# Auto-generated wrapper for shell_utils.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/shell_utils.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("shell_utils", "/data/data/com.termux/files/home/offline_ai/tools/shell_utils.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/shell_utils.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/shell_utils.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/shell_utils.py\n====================\nSafe subprocess helpers — shell=False by default, input sanitization.\n'
