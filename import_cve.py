import json
from pathlib import Path
from rag.store import _load, _save, _chunk, _keywords, _category_from_source

ROOT = Path.home() / "storage/external-1/offline_ai_knowledge/cybersecurity/cve/cvelistV5/cves"

# Optional: limit to recent years to start (set to None for full 1999-2026 run)
YEAR_LIMIT = None  # e.g. set to 2015 to only ingest CVE-2015 onward

BATCH_SAVE_EVERY = 2000

def extract_cve_text(data):
    try:
        cna = data["containers"]["cna"]
    except (KeyError, TypeError):
        return None

    cve_id = data.get("cveMetadata", {}).get("cveId", "UNKNOWN")

    descs = cna.get("descriptions", [])
    desc_text = ""
    for d in descs:
        if d.get("lang", "").startswith("en"):
            desc_text = d.get("value", "")
            break
    if not desc_text or desc_text.strip().lower() == "n/a":
        return None

    affected_parts = []
    for a in cna.get("affected", [])[:3]:
        vendor = a.get("vendor", "")
        product = a.get("product", "")
        if vendor and vendor != "n/a" and product and product != "n/a":
            affected_parts.append(f"{vendor} {product}")
    affected_str = ", ".join(affected_parts) if affected_parts else ""

    cwe_refs = []
    for pt in cna.get("problemTypes", []):
        for d in pt.get("descriptions", []):
            desc = d.get("description", "")
            if desc and desc.lower() != "n/a" and desc.upper().startswith("CWE"):
                cwe_refs.append(desc)

    text = f"{cve_id}: {desc_text}"
    if affected_str:
        text += f"\nAffected: {affected_str}"
    if cwe_refs:
        text += f"\nRelated weaknesses: {', '.join(cwe_refs)}"

    return text

def main():
    store = _load()
    existing = set(c["text"][:50] for c in store if c["source"] == "CVE")

    count = 0
    skipped = 0
    processed = 0

    for year_dir in sorted(ROOT.iterdir()):
        if not year_dir.is_dir():
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue
        if YEAR_LIMIT and year < YEAR_LIMIT:
            continue

        for range_dir in sorted(year_dir.iterdir()):
            if not range_dir.is_dir():
                continue
            for file in range_dir.glob("CVE-*.json"):
                processed += 1
                try:
                    with open(file) as f:
                        data = json.load(f)
                except Exception:
                    skipped += 1
                    continue

                text = extract_cve_text(data)
                if not text:
                    skipped += 1
                    continue

                for c in _chunk(text):
                    if c[:50] in existing:
                        continue
                    store.append({
                        "text": c,
                        "source": "CVE",
                        "category": "cve",
                        "keywords": _keywords(c)
                    })
                    existing.add(c[:50])
                    count += 1

                if processed % BATCH_SAVE_EVERY == 0:
                    _save(store)
                    print(f"[CVE] processed={processed} added={count} skipped={skipped} (year {year})")

    _save(store)
    print(f"\nDone. Processed {processed} files, added {count} chunks, skipped {skipped}.")

if __name__ == "__main__":
    main()
