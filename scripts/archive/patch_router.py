import re

path = "tools/router.py"
with open(path) as f:
    src = f.read()

orig = src
fixes_applied = []

# Fix 1: calc regex swallowing port ranges / CVE IDs (e.g. 4444-5555, CVE-2024-12345)
old1 = "    if re.search(r'[\\d]+\\s*[\\+\\-\\*\\/\\^]\\s*[\\d]+', text):\n        e = re.search(r'[\\d\\s\\+\\-\\*\\/\\^\\(\\)\\.]+', text)\n        return (\"calc\", e.group(0).strip()) if e else (None,None)"
new1 = "    if re.search(r'\\d+\\s*[\\+\\*\\/\\^]\\s*\\d+', text) or re.search(r'\\d+\\s+-\\s+\\d+', text):\n        e = re.search(r'[\\d\\s\\+\\-\\*\\/\\^\\(\\)\\.]+', text)\n        return (\"calc\", e.group(0).strip()) if e else (None,None)"
if old1 in src:
    src = src.replace(old1, new1)
    fixes_applied.append("1. calc regex (port-range/CVE misroute)")
else:
    fixes_applied.append("1. SKIPPED - exact text not found")

# Fix 2: add netcat handler (before "System tools" section)
old2 = "    # System tools\n    if any(w in lower for w in [\"my ram\",\"disk space\",\"sysinfo\",\"system info\"]):"
new2 = "    # Netcat\n    if re.match(r'^\\s*nc(at)?\\b', lower) or \"netcat\" in lower:\n        return (\"bash\", text.strip())\n\n    # System tools\n    if any(w in lower for w in [\"my ram\",\"disk space\",\"sysinfo\",\"system info\"]):"
if old2 in src:
    src = src.replace(old2, new2)
    fixes_applied.append("2. netcat handler added")
else:
    fixes_applied.append("2. SKIPPED - exact text not found")

# Fix 3: lower -> text + re.IGNORECASE (preserve filename case)
case_fixes = [
    ("rn = re.search(r'^(?:run|execute)\\s+([^\\s]+\\.(?:py|sh))', lower)",
     "rn = re.search(r'^(?:run|execute)\\s+([^\\s]+\\.(?:py|sh))', text, re.IGNORECASE)"),
    ("fm = re.search(r'read\\s+(?:file\\s+)?[\"\\']?([^\\s\"\\']+\\.\\w+)', lower)",
     "fm = re.search(r'read\\s+(?:file\\s+)?[\"\\']?([^\\s\"\\']+\\.\\w+)', text, re.IGNORECASE)"),
    ("nav = re.search(r'(?:navigate|list|show)\\s+(?:folder|dir|directory)?\\s*[\"\\']?([^\\s\"\\']+)', lower)",
     "nav = re.search(r'(?:navigate|list|show)\\s+(?:folder|dir|directory)?\\s*[\"\\']?([^\\s\"\\']+)', text, re.IGNORECASE)"),
    ("mv = re.search(r'move\\s+[\"\\']?([^\\s\"\\']+)[\"\\']?\\s+to\\s+[\"\\']?([^\\s\"\\']+)', lower)",
     "mv = re.search(r'move\\s+[\"\\']?([^\\s\"\\']+)[\"\\']?\\s+to\\s+[\"\\']?([^\\s\"\\']+)', text, re.IGNORECASE)"),
    ("cp = re.search(r'copy\\s+[\"\\']?([^\\s\"\\']+)[\"\\']?\\s+to\\s+[\"\\']?([^\\s\"\\']+)', lower)",
     "cp = re.search(r'copy\\s+[\"\\']?([^\\s\"\\']+)[\"\\']?\\s+to\\s+[\"\\']?([^\\s\"\\']+)', text, re.IGNORECASE)"),
    ("sc = re.search(r'scan\\s+(?:folder|dir|directory)?\\s*[\"\\']?([^\\s\"\\']+)', lower)",
     "sc = re.search(r'scan\\s+(?:folder|dir|directory)?\\s*[\"\\']?([^\\s\"\\']+)', text, re.IGNORECASE)"),
]
count3 = 0
for old, new in case_fixes:
    if old in src:
        src = src.replace(old, new)
        count3 += 1
fixes_applied.append(f"3. case-preserving regex: {count3}/6 applied")

# Fix 4: word-boundary tightening for recon/cert/investigate
word_fixes = [
    ('if "osint" in lower or "investigate" in lower or "full recon" in lower:',
     'if "osint" in lower or re.search(r"\\binvestigate\\b", lower) or "full recon" in lower:'),
    ('if "recon" in lower:',
     'if re.search(r"\\brecon\\b", lower):'),
    ('if "cert" in lower or "certificate" in lower or "ssl" in lower:',
     'if re.search(r"\\bcert\\b", lower) or "certificate" in lower or "ssl" in lower:'),
]
count4 = 0
for old, new in word_fixes:
    if old in src:
        src = src.replace(old, new)
        count4 += 1
fixes_applied.append(f"4. word-boundary tightening: {count4}/3 applied")

if src == orig:
    print("No changes made - nothing matched. Aborting, file untouched.")
else:
    with open(path, "w") as f:
        f.write(src)
    print("Patched", path)

for line in fixes_applied:
    print(" -", line)
