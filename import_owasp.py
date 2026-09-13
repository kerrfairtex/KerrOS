import os
import sys
from pathlib import Path

# Add project root to path for config import
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from rag.store import ingest_file
from core.config import BASE as CFG_BASE

# Resolve OWASP path from config.json knowledge_root
cfg_path = CFG_BASE / "config.json"
if cfg_path.exists():
    import json
    with open(cfg_path) as f:
        cfg = json.load(f)
    knowledge_root = cfg.get("knowledge_root", "./data")
    ROOT = (CFG_BASE / knowledge_root / "owasp").expanduser()
else:
    ROOT = CFG_BASE / "data" / "owasp"

count = 0

if ROOT.exists():
    for root, dirs, files in os.walk(ROOT):
        for f in files:
            if f.endswith(".md"):
                path = os.path.join(root, f)
                try:
                    ingest_file(path)
                    count += 1
                except Exception as e:
                    print(e)
else:
    print(f"OWASP knowledge directory not found: {ROOT}")

print()
print(f"Imported {count} OWASP cheat sheets.")
