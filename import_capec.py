import xml.etree.ElementTree as ET
from pathlib import Path

from rag.store import ingest_text

CAPEC = Path.home() / "storage/external-1/offline_ai_knowledge/cybersecurity/capec/capec.xml"

if not CAPEC.exists():
    raise SystemExit(f"Missing: {CAPEC}")

tree = ET.parse(CAPEC)
root = tree.getroot()

count = 0

for node in root.iter():
    if node.tag.endswith("Attack_Pattern"):
        capec_id = node.attrib.get("ID", "")
        name = node.attrib.get("Name", "")

        summary = ""

        for child in node:
            if child.tag.endswith("Description"):
                summary = "".join(child.itertext()).strip()
                break

        if not name:
            continue

        text = f"CAPEC-{capec_id}: {name}\n\n{summary}"

        ingest_text(text, source="CAPEC")

        count += 1

print(f"\nImported {count} CAPEC attack patterns.")
