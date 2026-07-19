import sys
from pathlib import Path
from rag.store import _load, _save, _chunk, _keywords, _category_from_source

ROOT = Path(sys.argv[1])
SOURCE_PREFIX = sys.argv[2]
BATCH_SAVE_EVERY = 500

def main():
    store = _load()
    existing = set(c["text"][:50] for c in store if c["source"].startswith(SOURCE_PREFIX))
    count = added = skipped = 0

    for file in ROOT.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in [".txt", ".md", ".html"]:
            continue
        count += 1
        try:
            text = file.read_text(errors="ignore")
        except Exception:
            skipped += 1
            continue
        if not text.strip():
            skipped += 1
            continue

        source = f"{SOURCE_PREFIX}_{file.stem}"
        for c in _chunk(text):
            if c[:50] in existing:
                continue
            store.append({
                "text": c, "source": source,
                "category": SOURCE_PREFIX.lower(),
                "keywords": _keywords(c)
            })
            existing.add(c[:50])
            added += 1

        if count % BATCH_SAVE_EVERY == 0:
            _save(store)
            print(f"[{SOURCE_PREFIX}] processed={count} added={added} skipped={skipped}")

    _save(store)
    print(f"\nDone. Processed {count}, added {added}, skipped {skipped}.")

if __name__ == "__main__":
    main()
