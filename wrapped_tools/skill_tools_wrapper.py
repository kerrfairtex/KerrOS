# Auto-generated wrapper for skill_tools.py
# Original module: /data/data/com.termux/files/home/offline_ai/tools/skill_tools.py

import importlib.util
import sys

# Load the original module
spec = importlib.util.spec_from_file_location("skill_tools", "/data/data/com.termux/files/home/offline_ai/tools/skill_tools.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load original tool: /data/data/com.termux/files/home/offline_ai/tools/skill_tools.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def execute(*args, **kwargs):
    import subprocess
    cmd = ['/data/data/com.termux/files/usr/bin/python3', '/data/data/com.termux/files/home/offline_ai/tools/skill_tools.py'] + list(map(str, args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def help():
    return '\ntools/skill_tools.py\n====================\nProgressive Disclosure skill system for KerrOS.\n\nThree-level architecture:\n  Level 0 — skills_list()    : compact index injected at session start (~3 k tokens)\n  Level 1 — skill_view()     : full skill doc loaded on demand (zero cost until called)\n  Level 2 — skill_manage()   : agents write/update/delete their own skills (self-evolution)\n\nSkill files live under  <WORKSPACE>/skills/<category>/<name>.md\nThe first line of each file (beginning with #) is the title.\nThe second non-blank line is used as the short description in the index.\n\nYAML tool catalogs from tools/registry/*.yaml are also surfaced as read-only skills\nunder the synthetic category "tool_catalog".\n'
