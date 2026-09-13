import xml.etree.ElementTree as ET
from pathlib import Path
from rag.store import ingest_text
import sys
import os

CAPEC = Path.home() / "offline_ai" / "test_capec.xml"
if not CAPEC.exists():
    CAPEC = os.environ.get('CAPEC_PATH') or Path.home() / 'offline_ai' / 'test_capec.xml'

if not CAPEC.exists():
    print(f"Warning: CAPEC data file not found at {CAPEC}")
    print("Skipping CAPEC import - knowledge database will remain incomplete")
    sys.exit(0)

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
print(f"[CAPEC] Import completed at {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

with open(Path.home() / "offline_ai" / "wiki_import_log.txt", "a") as log:
    log.write(f"{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [CAPEC] Imported {count} attack patterns\n")
