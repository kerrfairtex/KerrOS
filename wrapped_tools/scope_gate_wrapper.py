# Auto-generated wrapper for scope_gate.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/scope_gate.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("scope_gate", "/data/data/com.termux/files/home/offline_ai/tools/scope_gate.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/scope_gate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/scope_gate.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/scope_gate.py\n====================\nFail-closed authorization gate for active/offensive tools.\n\nPolicy (tool classes, arm defaults, messages) loads from\n`config/scope_policy.yaml`. Runtime allowlists (targets/CIDRs/arm window)\nremain in `config/scope.json`.\n\nAny tool that touches a real network target must pass through is_authorized()\nbefore it runs. Deploy tools require an explicit armed window.\n'
