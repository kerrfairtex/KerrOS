import os
from rag.store import ingest_file

ROOT = os.path.expanduser(
    "~/storage/external-1/offline_ai_knowledge/cybersecurity/owasp"
)

count = 0

for root, dirs, files in os.walk(ROOT):
    for f in files:
        if f.endswith(".md"):
            path = os.path.join(root, f)
            try:
                ingest_file(path)
                count += 1
            except Exception as e:
                print(e)

print()
print(f"Imported {count} OWASP cheat sheets.")
