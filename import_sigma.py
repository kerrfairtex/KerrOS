import yaml
from pathlib import Path
from rag.store import _load, _save, _chunk, _keywords

ROOT = Path.home() / "storage/external-1/offline_ai_knowledge/cybersecurity/sigma"
BATCH_SAVE_EVERY = 500

def extract_sigma_text(rule):
    title = rule.get("title", "")
    if not title:
        return None
    desc = rule.get("description", "")
    level = rule.get("level", "")
    logsource = rule.get("logsource", {})
    ls_str = ", ".join(f"{k}={v}" for k, v in logsource.items()) if isinstance(logsource, dict) else ""
    tags = rule.get("tags", [])
    tags_str = ", ".join(tags) if tags else ""
    falsepos = rule.get("falsepositives", "")
    if isinstance(falsepos, list):
        falsepos = ", ".join(falsepos)

    text = f"Sigma Rule: {title}"
    if desc:
        text += f"\n{desc}"
    if level:
        text += f"\nSeverity: {level}"
    if ls_str:
        text += f"\nLog source: {ls_str}"
    if tags_str:
        text += f"\nTags: {tags_str}"
    if falsepos:
        text += f"\nFalse positives: {falsepos}"
    return text

def main():
    store = _load()
    existing = set(c["text"][:50] for c in store if c["source"] == "Sigma")
    count = added = skipped = 0

    for file in ROOT.rglob("*.yml"):
        count += 1
        try:
            with open(file, errors="ignore") as f:
                rule = yaml.safe_load(f)
            if not isinstance(rule, dict):
                skipped += 1
                continue
        except Exception:
            skipped += 1
            continue

        text = extract_sigma_text(rule)
        if not text:
            skipped += 1
            continue

        for c in _chunk(text):
            if c[:50] in existing:
                continue
            store.append({"text": c, "source": "Sigma", "category": "sigma", "keywords": _keywords(c)})
            existing.add(c[:50])
            added += 1

        if count % BATCH_SAVE_EVERY == 0:
            _save(store)
            print(f"[Sigma] processed={count} added={added} skipped={skipped}")

    _save(store)
    print(f"\nDone. Processed {count}, added {added} chunks, skipped {skipped}.")

if __name__ == "__main__":
    main()
