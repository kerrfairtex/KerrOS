import json
from pathlib import Path

INDEX = Path.home() / "offline_ai/data/index.json"

with open(INDEX) as f:
    docs = json.load(f)

query = input("Search: ").lower()

for doc in docs:
    if query in doc["content"].lower():
        print("\nFOUND:")
        print(doc["path"])
        print(doc["content"][:500])
        break
