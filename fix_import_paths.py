#!/usr/bin/env python3
"""
Fix hardcoded storage/external-1 paths in import scripts.
Preserves original indentation. Backs up to .py.bak.
Does NOT reintroduce the pattern anywhere.
"""
import re
from pathlib import Path

ROOT = Path.home() / "offline_ai"

TARGETS = {
    "import_capec.py": ("CAPEC_PATH", "test_capec.xml"),
    "import_cisa.py": ("CISA_PATH", "test_cisa.json"),
    "import_cve.py": ("CVE_PATH", "data/raw/cve"),
    "import_cwe.py": ("CWE_PATH", "data/raw/cwe.xml"),
    "import_mitre_attack.py": ("MITRE_ATTACK_PATH", "data/raw/enterprise-attack.json"),
    "import_nist.py": ("NIST_PATH", "data/raw/nist"),
    "import_owasp.py": ("OWASP_PATH", "data/raw/owasp"),
    "import_sigma.py": ("SIGMA_PATH", "data/raw/sigma"),
    "import_yara.py": ("YARA_PATH", "data/raw/yara"),
}

print(f"{'SCRIPT':<26} {'ACTION':<12} DETAIL")
print("-" * 78)

for name, (env_var, fallback) in TARGETS.items():
    path = ROOT / name
    if not path.exists():
        print(f"{name:<26} {'SKIP':<12} not found")
        continue

    src = path.read_text()
    lines = src.splitlines()

    idx = None
    for i, line in enumerate(lines):
        if "storage/external-1/offline_ai_knowledge" in line:
            idx = i
            break

    if idx is None:
        print(f"{name:<26} {'OK':<12} no hardcoded path")
        continue

    offending = lines[idx]
    stripped = offending.lstrip()
    indent = offending[: len(offending) - len(stripped)]

    m = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\s*=', stripped)
    if not m:
        print(f"{name:<26} {'SKIP':<12} cannot parse: {stripped[:50]}")
        continue
    varname = m.group(1)

    replacement = f"{indent}{varname} = os.environ.get('{env_var}') or Path.home() / 'offline_ai' / '{fallback}'"

    if not re.search(r"^import\s+os", src, re.MULTILINE):
        src = "import os\n" + src
    if not re.search(r"^from pathlib import Path", src, re.MULTILINE):
        src = "from pathlib import Path\n" + src

    new_lines = lines[:idx] + [replacement] + lines[idx + 1:]
    body = "\n".join(new_lines)
    if not body.endswith("\n"):
        body += "\n"

    (path.with_suffix(path.suffix + ".bak")).write_text(src)
    path.write_text(body)
    print(f"{name:<26} {'PATCHED':<12} {varname} <- env:{env_var} | fallback:{fallback}")

print("-" * 78)
print("Revert: for f in import_*.py.bak; do mv \"$f\" \"${f%.bak}\"; done")
