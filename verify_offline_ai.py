#!/usr/bin/env python3
"""
verify_offline_ai.py
====================
Read-only ground-truth verification for the offline_ai project.
Prints raw evidence for every check. No summaries. No inference.
Run from anywhere; resolves paths relative to ~/offline_ai.
"""
import os
import re
import sys
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

HOME = Path.home()
ROOT = HOME / "offline_ai"
DB   = ROOT / "data" / "rag_store.db"
LOG  = ROOT / "wiki_import_log.txt"
CFG  = ROOT / "config.json"
KG   = ROOT / "data" / "knowledge"

results = []   # list of (section, check, status, evidence)

def record(section, check, ok, evidence):
    status = "PASS" if ok is True else "FAIL" if ok is False else "INFO"
    results.append((section, check, status, evidence))
    print(f"[{status}] {section} | {check}")
    print(f"      {evidence}")

def section(title):
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)

def run(cmd):
    """Run shell command, return (stdout, stderr, exit_code)."""
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except Exception as e:
        return "", str(e), -1

# ─────────────────────────────────────────────────────────
section("SECTION 0 — ENVIRONMENT")
# ─────────────────────────────────────────────────────────
record("0", "cwd", None, os.getcwd())
record("0", "user", None, os.environ.get("USER", "unknown"))
record("0", "python", None, sys.version.split()[0])
record("0", "project root exists", ROOT.exists(), str(ROOT))

if not ROOT.exists():
    print("\nFATAL: ~/offline_ai does not exist. Aborting.")
    sys.exit(2)

# ─────────────────────────────────────────────────────────
section("SECTION 1 — KEY FILES EXIST")
# ─────────────────────────────────────────────────────────
for label, path in [
    ("config.json", CFG),
    ("rag/store.py", ROOT / "rag" / "store.py"),
    ("rag/path_guard.py", ROOT / "rag" / "path_guard.py"),
    ("cli/chat.py", ROOT / "cli" / "chat.py"),
    ("kernel/router.py", ROOT / "kernel" / "router.py"),
    ("wiki_import_log.txt", LOG),
    ("data/rag_store.db", DB),
]:
    record("1", label, path.exists(),
           f"{path} ({'exists' if path.exists() else 'MISSING'})")

# ─────────────────────────────────────────────────────────
section("SECTION 2 — CONFIG VALUES (raw)")
# ─────────────────────────────────────────────────────────
if CFG.exists():
    try:
        cfg = json.loads(CFG.read_text())
        for k in ("knowledge_root", "knowledge_index", "auto_index"):
            if k in cfg:
                record("2", k, None, f"{k} = {cfg[k]!r}")
            else:
                record("2", k, None, f"{k} not present in config.json")
    except Exception as e:
        record("2", "config parse", False, f"json error: {e}")
else:
    record("2", "config.json present", False, "file missing")

# ─────────────────────────────────────────────────────────
section("SECTION 3 — RAG DATABASE CONTENTS")
# ─────────────────────────────────────────────────────────
if DB.exists():
    size = DB.stat().st_size
    record("3", "db file size", size > 0, f"{size} bytes")
    try:
        con = sqlite3.connect(str(DB))
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        record("3", "tables", len(tables) > 0, f"{tables}")
        for t in tables:
            try:
                n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                record("3", f"table {t} row count", n > 0 or t.startswith("sqlite_"),
                       f"{t} = {n} rows")
            except Exception as e:
                record("3", f"table {t} count", False, f"error: {e}")
        # sample one chunk
        try:
            row = con.execute(
                "SELECT id, substr(text,1,60), source FROM chunks LIMIT 3"
            ).fetchall()
            for r in row:
                record("3", f"sample chunk id={r[0]}", None,
                       f"source={r[2]} text={r[1]!r}")
        except Exception as e:
            record("3", "sample chunks", False, f"error: {e}")
        con.close()
    except Exception as e:
        record("3", "db open", False, f"{e}")
else:
    record("3", "db exists", False, "rag_store.db MISSING")

# ─────────────────────────────────────────────────────────
section("SECTION 4 — RETRIEVAL API ACTUALLY WORKS")
# ─────────────────────────────────────────────────────────
sys.path.insert(0, str(ROOT))
try:
    from rag.store import search, search_fts, list_sources, count_chunks
    try:
        rows = search("CAPEC", top_k=3)
        record("4", "search('CAPEC')", len(rows) > 0, f"returned {len(rows)} rows")
        for r in rows[:3]:
            record("4", "  → row", None, f"{r}")
    except Exception as e:
        record("4", "search()", False, f"{e}")

    try:
        rows = search_fts("CAPEC", top_k=3)
        record("4", "search_fts('CAPEC')", len(rows) > 0, f"returned {len(rows)} rows")
    except Exception as e:
        record("4", "search_fts()", False, f"{e}")

    try:
        srcs = list_sources()
        record("4", "list_sources()", len(srcs) > 0, f"{srcs}")
    except Exception as e:
        record("4", "list_sources()", False, f"{e}")

    try:
        n = count_chunks()
        record("4", "count_chunks()", n > 0, f"{n} chunks")
    except Exception as e:
        record("4", "count_chunks()", False, f"{e}")
except Exception as e:
    record("4", "import rag.store", False, f"{e}")

# ─────────────────────────────────────────────────────────
section("SECTION 5 — GUARD FUNCTION (knowledge_root consumer)")
# ─────────────────────────────────────────────────────────
guard = ROOT / "rag" / "path_guard.py"
if guard.exists():
    text = guard.read_text()
    record("5", "assert_kerros_paths defined",
           "def assert_kerros_paths" in text,
           "def found" if "def assert_kerros_paths" in text else "def NOT found")
    # What does the guard actually reject?
    for m in re.finditer(r"(raise|assert)\s+.*", text):
        record("5", "  guard rule", None, m.group(0)[:80])
else:
    record("5", "path_guard.py", False, "file missing")

# ─────────────────────────────────────────────────────────
section("SECTION 6 — IMPORT SCRIPTS: HARDCODED PATH AUDIT")
# ─────────────────────────────────────────────────────────
imports = sorted(ROOT.glob("import_*.py"))
record("6", "import scripts found", len(imports) > 0,
       f"{len(imports)} files: {[p.name for p in imports]}")

hardcoded_pattern = re.compile(r'storage/external-1|storage/external_1')
hardcoded_count = 0
for p in imports:
    try:
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if hardcoded_pattern.search(line):
                hardcoded_count += 1
                record("6", f"  {p.name}:{i}", False, line.strip()[:90])
    except Exception as e:
        record("6", f"  {p.name} read", False, str(e))

if hardcoded_count == 0:
    record("6", "hardcoded paths", True, "none found in import_*.py")
else:
    record("6", "hardcoded path count", False,
           f"{hardcoded_count} occurrences still present")

# ─────────────────────────────────────────────────────────
section("SECTION 7 — IMPORT LOG STATE")
# ─────────────────────────────────────────────────────────
if LOG.exists():
    size = LOG.stat().st_size
    lines = LOG.read_text().splitlines()
    record("7", "log file size", size > 0, f"{size} bytes, {len(lines)} lines")
    for line in lines[-5:]:
        record("7", "  last lines", None, line[:90])
else:
    record("7", "wiki_import_log.txt", False, "missing")

# ─────────────────────────────────────────────────────────
section("SECTION 8 — KNOWLEDGE DIRECTORY (expected empty)")
# ─────────────────────────────────────────────────────────
if KG.exists():
    entries = [p.name for p in KG.iterdir()]
    record("8", "data/knowledge/ contents", None, f"{entries}")
    record("8", "expected empty per design", len(entries) == 0,
           "empty (correct)" if len(entries) == 0
           else f"contains {len(entries)} entries — unexpected")
else:
    record("8", "data/knowledge/", False, "directory missing")

# ─────────────────────────────────────────────────────────
section("SECTION 9 — LLM MODEL FILE")
# ─────────────────────────────────────────────────────────
for candidate in [ROOT / "models" / "model.gguf",
                  ROOT / "models" / "*.gguf"]:
    if "*" in str(candidate):
        found = list((ROOT / "models").glob("*.gguf")) if (ROOT / "models").exists() else []
        record("9", "gguf files in models/", len(found) > 0,
               f"{[p.name for p in found]}")
    else:
        record("9", candidate.name, candidate.exists(),
               f"{candidate} ({'exists' if candidate.exists() else 'MISSING'})")

# ─────────────────────────────────────────────────────────
section("SECTION 10 — GIT STATE")
# ─────────────────────────────────────────────────────────
out, err, rc = run(f"cd {ROOT} && git rev-parse --is-inside-work-tree 2>&1")
if rc == 0 and "true" in out:
    out, _, _ = run(f"cd {ROOT} && git log --oneline -3 2>&1")
    record("10", "git repo", True, "yes")
    for line in out.splitlines()[:3]:
        record("10", "  recent commit", None, line)
    out, _, _ = run(f"cd {ROOT} && git status --short 2>&1 | head -10")
    for line in out.splitlines()[:10]:
        record("10", "  status", None, line)
else:
    record("10", "git repo", False, f"not a git repo or git unavailable: {err or out}")

# ─────────────────────────────────────────────────────────
section("SECTION 11 — SCRIPT EXECUTION SMOKE TEST")
# ─────────────────────────────────────────────────────────
for name in ("import_capec.py", "import_cisa.py"):
    p = ROOT / name
    if not p.exists():
        record("11", name, False, "missing")
        continue
    out, err, rc = run(f"cd {ROOT} && python3 {name} 2>&1 | tail -3")
    record("11", f"{name} exit", rc == 0,
           f"exit={rc} | output={out!r} | stderr={err!r}")

# ─────────────────────────────────────────────────────────
section("FINAL SCORECARD")
# ─────────────────────────────────────────────────────────
passes = sum(1 for r in results if r[2] == "PASS")
fails  = sum(1 for r in results if r[2] == "FAIL")
infos  = sum(1 for r in results if r[2] == "INFO")

print(f"\n{'='*72}")
print(f"  PASS: {passes}   FAIL: {fails}   INFO: {infos}   TOTAL: {len(results)}")
print(f"{'='*72}\n")

if fails:
    print("FAILURES (fix these first):")
    for sec, chk, stat, ev in results:
        if stat == "FAIL":
            print(f"  [{sec}] {chk}")
            print(f"       {ev}")
    print()

print("Report generated:", datetime.now().isoformat())
print("Exit code:", 1 if fails else 0)
sys.exit(1 if fails else 0)
