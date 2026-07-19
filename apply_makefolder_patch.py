"""
Run from ~/offline_ai:
    python3 apply_makefolder_patch.py
Patches tools/router.py. Makes tools/router.py.bak4 first.
"""
import shutil

PATH = "tools/router.py"

with open(PATH) as f:
    content = f.read()

# --- Fix 1: name-capture regex was grabbing "in" from phrasing like
#     "make a folder in termux home directory named GOALTEST2" ------
anchor1 = (
    '    fc = re.search(r\'(?:create|make)\\s+(?:a\\s+)?folder\\s+(?:called\\s+)?["\\\']?([^\\s"\\\']+)\', lower)\n'
    '    if fc: return ("make_folder", fc.group(1))\n'
)
replacement1 = (
    '    fc = re.search(r\'(?:create|make)\\s+(?:a\\s+)?folder\\b.*?\\b(?:named|called)\\s+["\\\']?([^\\s"\\\']+)\', lower)\n'
    '    if not fc:\n'
    '        fc = re.search(r\'(?:create|make)\\s+(?:a\\s+)?folder\\s+(?:called\\s+)?["\\\']?([^\\s"\\\']+)\', lower)\n'
    '        if fc and fc.group(1) in ("in", "the", "a", "at", "on", "inside"):\n'
    '            fc = None\n'
    '    if fc: return ("make_folder", fc.group(1))\n'
)
if anchor1 not in content:
    raise SystemExit(f"ABORT (fix 1): anchor not found — no changes made.\nLooking for:\n{anchor1!r}")

# --- Fix 2: _resolve_path fallback anchored to cwd instead of true home ---
anchor2 = (
    'def _resolve_path(p):\n'
    '    parts = p.replace("\\\\", "/").split("/", 1)\n'
    '    key = parts[0].lower()\n'
    '    if key in STORAGE_SHORTCUTS:\n'
    '        base = os.path.expanduser(STORAGE_SHORTCUTS[key])\n'
    '        rest = parts[1] if len(parts) > 1 else ""\n'
    '        return os.path.join(base, rest) if rest else base\n'
    '    return os.path.expanduser(p)\n'
)
replacement2 = (
    'def _resolve_path(p):\n'
    '    parts = p.replace("\\\\", "/").split("/", 1)\n'
    '    key = parts[0].lower()\n'
    '    if key in STORAGE_SHORTCUTS:\n'
    '        base = os.path.expanduser(STORAGE_SHORTCUTS[key])\n'
    '        rest = parts[1] if len(parts) > 1 else ""\n'
    '        return os.path.join(base, rest) if rest else base\n'
    '    p = os.path.expanduser(p)\n'
    '    if not os.path.isabs(p):\n'
    '        # Bare relative names anchor to true Termux home, not the\n'
    '        # directory the script happened to be launched from.\n'
    '        p = os.path.join(os.path.expanduser("~"), p)\n'
    '    return p\n'
)
if anchor2 not in content:
    raise SystemExit(f"ABORT (fix 2): anchor not found — no changes made.\nLooking for:\n{anchor2!r}")

shutil.copy(PATH, PATH + ".bak4")
content = content.replace(anchor1, replacement1, 1)
content = content.replace(anchor2, replacement2, 1)
with open(PATH, "w") as f:
    f.write(content)

print(f"Patched {PATH}. Backup at {PATH}.bak4")
print("Now run: python3 -m py_compile tools/router.py && echo SYNTAX_OK")
