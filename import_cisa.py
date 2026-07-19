import json
from pathlib import Path
from rag.store import _load, _save, _chunk, _keywords

CISA = Path.home() / "storage/external-1/offline_ai_knowledge/cybersecurity/cisa/known_exploited_vulnerabilities.json"

def main():
    with open(CISA) as f:
        data = json.load(f)

    vulns = data.get("vulnerabilities", [])
    store = _load()
    existing = set(c["text"][:50] for c in store if c["source"] == "CISA_KEV")
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

        for c in _chunk(text):
            if c[:50] in existing:
                continue
            store.append({"text": c, "source": "CISA_KEV", "category": "cisa", "keywords": _keywords(c)})
            existing.add(c[:50])
            added += 1

    _save(store)
    print(f"Done. {len(vulns)} KEV entries processed, {added} chunks added.")

if __name__ == "__main__":
    main()
