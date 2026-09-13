# Auto-generated wrapper for shell_hooks.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/shell_hooks.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("shell_hooks", "/data/data/com.termux/files/home/offline_ai/tools/shell_hooks.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/shell_hooks.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/shell_hooks.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/shell_hooks.py\n====================\nShell-script lifecycle hooks (ADR-065).\n\nConfig (config.json ``shell_hooks`` or env KERROS_SHELL_HOOKS=1):\n  {\n    "enabled": true,\n    "auto_accept": false,\n    "hooks": [\n      {"event": "pre_tool_call", "command": "scripts/hooks/pre_tool.py"},\n      {"event": "post_tool_call", "command": "scripts/hooks/post_tool.py"},\n      {"event": "session_start", "command": "scripts/hooks/session_start.sh"}\n    ]\n  }\n\nScripts receive JSON on stdin; pre_tool scripts may print\n{"decision":"block","reason":"..."} to deny. Commands are argv-split\n(shell=False) and must stay under the workspace.\n'
