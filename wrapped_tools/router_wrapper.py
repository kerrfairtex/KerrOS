# Auto-generated wrapper for router.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/router.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("router", "/data/data/com.termux/files/home/offline_ai/tools/router.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/router.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/router.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\nDeprecation shim — kernel/router.py is now the canonical location (KOS-004).\nRe-exports the same names so existing `from tools.router import ...` call\nsites keep working without changes. New code should import from\nkernel.router directly.\n'
