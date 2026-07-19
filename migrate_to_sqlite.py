import ijson
import sqlite3
import os

BASE = os.path.expanduser("~/offline_ai")
JSON_PATH = f"{BASE}/data/rag_store.json"
DB_PATH = f"{BASE}/data/rag_store.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("""
    CREATE TABLE chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        source TEXT NOT NULL,
        category TEXT,
        keywords TEXT
    )
""")
conn.execute("CREATE INDEX idx_category ON chunks(category)")
conn.execute("CREATE INDEX idx_source ON chunks(source)")
conn.commit()

count = 0
skipped = 0
BATCH_SIZE = 1000
batch = []

with open(JSON_PATH, "rb") as f:
    for obj in ijson.items(f, "item"):
        if not isinstance(obj, dict) or "text" not in obj or "source" not in obj:
            skipped += 1
            continue

        text = obj.get("text", "")
        source = obj.get("source", "")
        category = obj.get("category", "general")
        keywords = ",".join(obj.get("keywords", []))

        batch.append((text, source, category, keywords))
        count += 1

        if len(batch) >= BATCH_SIZE:
            conn.executemany(
                "INSERT INTO chunks (text, source, category, keywords) VALUES (?, ?, ?, ?)",
                batch
            )
            conn.commit()
            batch = []
            print(f"Migrated {count} entries...")

if batch:
    conn.executemany(
        "INSERT INTO chunks (text, source, category, keywords) VALUES (?, ?, ?, ?)",
        batch
    )
    conn.commit()

conn.close()
print(f"\nDone. Migrated {count} entries, skipped {skipped} malformed entries.")
print(f"Database: {DB_PATH}")
