# Auto-generated wrapper for skills_hub.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/skills_hub.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("skills_hub", "/data/data/com.termux/files/home/offline_ai/tools/skills_hub.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/skills_hub.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/skills_hub.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/skills_hub.py\n===================\nLocal skills hub: install / uninstall / lockfile / quarantine (ADR-064).\n\nInstall sources (default Soft):\n  - local path (file or directory of markdown)\n  - optional http(s) URL when KERROS_SKILLS_HUB_LIVE=1\n\nInstalled skills land under skills/<category>/<name>.md.\nQuarantined copies go to data/skills_hub/quarantine/.\nProvenance lock: data/skills_hub/lock.json\n'
