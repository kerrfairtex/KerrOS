import json
from pathlib import Path

from rag.store import ingest_text

ATTACK = Path.home() / "storage/external-1/offline_ai_knowledge/cybersecurity/mitre_attack/enterprise-attack.json"

if not ATTACK.exists():
    raise SystemExit(f"Missing: {ATTACK}")

with ATTACK.open("r", encoding="utf-8") as f:
    data = json.load(f)

count = 0

for obj in data.get("objects", []):
    if obj.get("type") != "attack-pattern":
        continue

    name = obj.get("name", "")
    desc = obj.get("description", "")

    if not name or not desc:
        continue

    text = f"Technique: {name}\n\n{desc}"
    ingest_text(text, source="MITRE_ATT&CK")
    count += 1

print(f"\nImported {count} ATT&CK techniques.")
