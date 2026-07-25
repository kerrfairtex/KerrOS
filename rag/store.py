import os, json, re, sqlite3

BASE = os.path.expanduser("~/offline_ai")

def _load_cfg():
    try:
        from kernel.config import load_config
        return load_config().values, str(load_config().base)
    except Exception:
        cfg_path = f"{BASE}/config.json"
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                return json.load(f), BASE
        return {}, BASE

_CFG, _BASE = _load_cfg()
CFG = _CFG
DB_PATH = os.path.join(_BASE, "data", "rag_store.db")

KNOWLEDGE_ROOT = os.path.expanduser(
    CFG.get("knowledge_root", "~/storage/external-1/offline_ai_knowledge")
)
KNOWLEDGE_INDEX = os.path.expanduser(
    CFG.get("knowledge_index", "~/offline_ai/data/knowledge")
)


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            source TEXT NOT NULL,
            category TEXT,
            keywords TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON chunks(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON chunks(source)")
    conn.commit()
    conn.close()


_ensure_schema()


def _normalize(text):
    return re.sub(r'[^\w\s]', '', text.lower())


def _keywords(text):
    stop = {"the","a","an","is","are","was","were","be","been","being",
            "have","has","had","do","does","did","will","would","could",
            "should","may","might","shall","can","of","in","on","at",
            "to","for","with","by","from","as","it","its","this","that"}
    words = _normalize(text).split()
    return [w for w in words if w not in stop and len(w) > 2]


def _chunk(text, size=120, overlap=30):
    words = text.split()
    out, i = [], 0
    while i < len(words):
        chunk = " ".join(words[i:i+size])
        if len(chunk.strip()) > 20:
            out.append(chunk)
        i += size - overlap
    return out


def _category_from_source(source):
    s = source.lower()
    if "sigma" in s: return "sigma"
    if "yara" in s: return "yara"
    if "cisa" in s or "kev" in s: return "cisa"
    if "cwe" in s: return "cwe"
    if "owasp" in s or "cheat_sheet" in s.replace(" ","_"): return "owasp"
    if "mitre" in s: return "mitre"
    if "capec" in s: return "capec"
    if "nist" in s: return "nist"
    if "cve" in s: return "cve"
    if "rfc" in s or "networking" in s: return "networking"
    if "wikipedia" in s: return "wikipedia"
    if "linux" in s: return "linux"
    if "python" in s or "programming" in s: return "programming"
    if "git" in s: return "git"
    return "general"


def ingest_text(text, source="manual"):
    chunks = _chunk(text)
    category = _category_from_source(source)
    conn = _conn()

    existing = set(
        row[0][:50] for row in
        conn.execute("SELECT text FROM chunks WHERE source = ?", (source,))
    )

    added = 0
    batch = []
    for c in chunks:
        if c[:50] in existing:
            continue
        batch.append((c, source, category, ",".join(_keywords(c))))
        existing.add(c[:50])
        added += 1

    if batch:
        conn.executemany(
            "INSERT INTO chunks (text, source, category, keywords) VALUES (?, ?, ?, ?)",
            batch
        )
        conn.commit()
    conn.close()
    print(f"[RAG] +{added} chunks from '{source}'")


def ingest_file(path):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        print(f"[RAG] Not found: {path}"); return
    with open(path) as f: text = f.read()
    ingest_text(text, os.path.basename(path))


def search(query, top_k=3):
    qk = set(_keywords(query))
    if not qk:
        return []

    conn = _conn()
    like_clauses = " OR ".join(["keywords LIKE ?"] * len(qk))
    params = [f"%{w}%" for w in qk]

    rows = conn.execute(
        f"SELECT text, source, keywords FROM chunks WHERE {like_clauses}",
        params
    ).fetchall()
    conn.close()

    results = []
    for text, source, keywords in rows:
        ck = set(keywords.split(",")) if keywords else set()
        overlap = len(qk & ck)
        if overlap == 0:
            continue
        bonus = 2 if any(w in text.lower() for w in qk) else 0
        results.append((overlap + bonus, text, source))

    results.sort(reverse=True)
    return results[:top_k]


def search_by_category(query, category=None, top_k=4):
    qk = set(_keywords(query))
    if not qk:
        return []

    conn = _conn()
    if category:
        rows = conn.execute(
            "SELECT text, source, keywords FROM chunks WHERE category = ?",
            (category,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT text, source, keywords FROM chunks").fetchall()
    conn.close()

    results = []
    for text, source, keywords in rows:
        ck = set(keywords.split(",")) if keywords else set()
        overlap = len(qk & ck)
        if overlap == 0:
            continue
        bonus = 2 if any(w in text.lower() for w in qk) else 0
        results.append((overlap + bonus, text, source))

    results.sort(reverse=True)
    if category and len(results) < top_k:
        extra = search(query, top_k=top_k - len(results))
        results.extend(extra)
    return results[:top_k]


def search_multi_category(query, categories, top_k=4):
    qk = set(_keywords(query))
    if not qk:
        return []

    conn = _conn()
    per_cat = max(1, top_k // len(categories))
    results = []
    seen = set()

    for cat in categories:
        rows = conn.execute(
            "SELECT text, source, keywords FROM chunks WHERE category = ?",
            (cat,)
        ).fetchall()

        cat_hits = []
        for text, source, keywords in rows:
            ck = set(keywords.split(",")) if keywords else set()
            overlap = len(qk & ck)
            if overlap == 0:
                continue
            bonus = 2 if any(w in text.lower() for w in qk) else 0
            cat_hits.append((overlap + bonus, text, source))

        cat_hits.sort(reverse=True)
        for hit in cat_hits[:per_cat]:
            key = hit[1][:50]
            if key not in seen:
                results.append(hit)
                seen.add(key)

    conn.close()
    results.sort(reverse=True)
    return results[:top_k]


def search_exact_id(query):
    m = re.search(r'(cve-\d{4}-\d+|cwe-\d+|capec-\d+)', query.lower())
    if not m:
        return []
    target = m.group(1).upper()

    conn = _conn()
    rows = conn.execute(
        "SELECT text, source FROM chunks WHERE text LIKE ?",
        (f"{target}%",)
    ).fetchall()
    conn.close()

    return [(10, text, source) for text, source in rows][:3]


def backfill_categories():
    conn = _conn()
    rows = conn.execute("SELECT id, source, category FROM chunks").fetchall()
    changed = 0
    for id_, source, category in rows:
        correct = _category_from_source(source)
        if correct != category:
            conn.execute("UPDATE chunks SET category = ? WHERE id = ?", (correct, id_))
            changed += 1
    conn.commit()
    conn.close()
    print(f"Backfilled/corrected {changed} entries.")


def list_sources():
    conn = _conn()
    rows = conn.execute("SELECT DISTINCT source FROM chunks").fetchall()
    conn.close()
    return [r[0] for r in rows]
