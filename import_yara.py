from pathlib import Path
from rag.store import _load, _save, _chunk, _keywords

ROOT = Path.home() / "storage/external-1/offline_ai_knowledge/cybersecurity/yara"
BATCH_SAVE_EVERY = 200

def main():
    store = _load()
    existing = set(c["text"][:50] for c in store if c["source"] == "YARA")
    count = added = skipped = 0

    for file in ROOT.rglob("*.yar*"):
        count += 1
        try:
            text = file.read_text(errors="ignore")
        except Exception:
            skipped += 1
            continue

        if not text.strip():
            skipped += 1
            continue

        text = f"YARA rule file: {file.stem}\n\n{text}"

        for c in _chunk(text):
            if c[:50] in existing:
                continue
            store.append({"text": c, "source": "YARA", "category": "yara", "keywords": _keywords(c)})
            existing.add(c[:50])
            added += 1

        if count % BATCH_SAVE_EVERY == 0:
            _save(store)
            print(f"[YARA] processed={count} added={added} skipped={skipped}")

    _save(store)
    print(f"\nDone. Processed {count}, added {added} chunks, skipped {skipped}.")

if __name__ == "__main__":
    main()
