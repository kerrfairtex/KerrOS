import json
from pathlib import Path
from rag.store import _chunk, _keywords, ingest_text
import sys
import os
from datetime import datetime

CISA = Path.home() / "offline_ai" / "test_cisa.json"
if not CISA.exists():
    CISA = os.environ.get('CISA_PATH') or Path.home() / 'offline_ai' / 'test_cisa.json'

if not CISA.exists():
    print(f"Warning: CISA data file not found at {CISA}")
    print("Skipping CISA import - knowledge database will remain incomplete")
    sys.exit(0)

def main():
    with open(CISA) as f:
        data = json.load(f)

    vulns = data.get("vulnerabilities", [])
    added = 0

    for v in vulns:
        cve = v.get("cveID", "")
        vendor = v.get("vendorProject", "")
        product = v.get("product", "")
        name = v.get("vulnerabilityName", "")
        desc = v.get("shortDescription", "")
        action = v.get("requiredAction", "")
        ransomware = v.get("knownRansomwareCampaignUse", "")

        text = f"{cve} (CISA KEV): {name}\nVendor/Product: {vendor} {product}\n{desc}"
        if action:
            text += f"\nRequired action: {action}"
        if ransomware and ransomware.lower() != "unknown":
            text += f"\nKnown ransomware use: {ransomware}"

        ingest_text(text, source="CISA_KEV")
        added += 1

    print(f"Done. {len(vulns)} KEV entries processed, {added} chunks added.")
    print(f"[CISA] Import completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Log successful import
    with open(Path.home() / "offline_ai" / "wiki_import_log.txt", "a") as log:
        log.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [CISA] Imported {len(vulns)} KEV entries, {added} chunks added\n")

if __name__ == "__main__":
    main()
