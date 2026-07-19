import xml.etree.ElementTree as ET
from pathlib import Path
from rag.store import _load, _save, _chunk, _keywords

CWE = Path.home() / "storage/external-1/offline_ai_knowledge/cybersecurity/cwe/cwec_v4.20.xml"

if not CWE.exists():
    raise SystemExit(f"Missing: {CWE}")

tree = ET.parse(CWE)
root = tree.getroot()

store = _load()
existing = set(c["text"][:50] for c in store if c["source"] == "CWE")
count = added = 0

for node in root.iter():
    if node.tag.endswith("Weakness"):
        cwe_id = node.attrib.get("ID", "")
        name = node.attrib.get("Name", "")
        if not name:
            continue

        description = ""
        extended = ""
        for child in node:
            if child.tag.endswith("Description") and not child.tag.endswith("Extended_Description"):
                description = "".join(child.itertext()).strip()
            elif child.tag.endswith("Extended_Description"):
                extended = "".join(child.itertext()).strip()

        text = f"CWE-{cwe_id}: {name}\n\n{description}"
        if extended:
            text += f"\n\n{extended}"

        for c in _chunk(text):
            if c[:50] in existing:
                continue
            store.append({
                "text": c, "source": "CWE", "category": "cwe",
                "keywords": _keywords(c)
            })
            existing.add(c[:50])
            added += 1

        count += 1
        if count % 100 == 0:
            _save(store)
            print(f"[CWE] processed={count} added={added}")

_save(store)
print(f"\nImported {count} CWE weaknesses, {added} chunks added.")
