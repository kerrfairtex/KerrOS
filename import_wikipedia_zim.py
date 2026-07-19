import re, sys, sqlite3
import requests
from bs4 import BeautifulSoup
from rag.store import _chunk, _keywords, DB_PATH

KIWIX_BASE = "http://localhost:8080"
BOOK = "wikipedia_en_top_nopic_2026-06"
TARGET_COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
BATCH_SIZE = 100
SOURCE_PREFIX = "Wikipedia"


def get_random_article():
    r = requests.get(f"{KIWIX_BASE}/random?content={BOOK}", allow_redirects=False, timeout=10)
    loc = r.headers.get("Location", "")
    if f"/content/{BOOK}/" in loc:
        return loc.split(f"/content/{BOOK}/")[-1]
    return None


def fetch_article_text(title):
    url = f"{KIWIX_BASE}/content/{BOOK}/{title}"
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")
    content = soup.find("div", id="mw-content-text")
    if not content:
        return None, None

    for tag in content.find_all(["style", "script", "sup"]):
        tag.decompose()
    for tag in content.find_all(class_=re.compile("sidebar|infobox|navbox|hatnote|mw-editsection|reflist|reference")):
        tag.decompose()

    paragraphs = content.find_all("p")
    text = "\n".join(p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True))
    return title.replace("_", " "), text


def main():
    conn = sqlite3.connect(DB_PATH)

    existing_sources = set(
        row[0] for row in
        conn.execute("SELECT DISTINCT source FROM chunks WHERE category = 'wikipedia'")
    )

    seen_titles = set()
    fetched = added = skipped = 0
    batch = []

    while fetched < TARGET_COUNT:
        title = get_random_article()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        real_title, text = fetch_article_text(title)
        fetched += 1

        source = f"{SOURCE_PREFIX}_{real_title[:40]}" if real_title else None

        if not text or len(text.strip()) < 200 or (source and source in existing_sources):
            skipped += 1
            continue

        existing_texts = set(
            row[0][:50] for row in
            conn.execute("SELECT text FROM chunks WHERE source = ?", (source,))
        )

        for c in _chunk(text):
            if c[:50] in existing_texts:
                continue
            batch.append((c, source, "wikipedia", ",".join(_keywords(c))))
            existing_texts.add(c[:50])
            added += 1

        existing_sources.add(source)

        if fetched % BATCH_SIZE == 0:
            if batch:
                conn.executemany(
                    "INSERT INTO chunks (text, source, category, keywords) VALUES (?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                batch = []
            print(f"[Wikipedia] fetched={fetched}/{TARGET_COUNT} added={added} skipped={skipped}")

    if batch:
        conn.executemany(
            "INSERT INTO chunks (text, source, category, keywords) VALUES (?, ?, ?, ?)",
            batch
        )
        conn.commit()

    conn.close()
    print(f"\nDone. Fetched {fetched} articles, added {added} chunks, skipped {skipped}.")


if __name__ == "__main__":
    main()
