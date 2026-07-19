from pathlib import Path
from rag.store import ingest_text
from pypdf import PdfReader

ROOT = Path.home() / "storage/external-1/offline_ai_knowledge/cybersecurity/nist"

count = 0

for file in ROOT.rglob("*"):
    suffix = file.suffix.lower()

    if suffix == ".pdf":
        try:
            reader = PdfReader(str(file))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            print(f"[skip] {file.name}: {e}")
            continue
    elif suffix in [".txt", ".md", ".html"]:
        try:
            text = file.read_text(errors="ignore")
        except Exception:
            continue
    else:
        continue

    if not text.strip():
        print(f"[empty] {file.name}")
        continue

    ingest_text(text, source=f"NIST_{file.stem}")
    count += 1

print(f"\nImported {count} NIST documents.")
