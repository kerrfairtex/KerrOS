#!/usr/bin/env python3
"""One-off: bypass the adapter's error handling entirely and print the raw
JSON OpenRouter actually sent back for the two models that failed."""
import os, json, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
key = os.getenv("OPENROUTER_API_KEY", "")
models = ["inclusionai/ling-3.0-flash:free", "poolside/laguna-xs-2.1:free"]

for model_id in models:
    print(f"\n=== {model_id} ===")
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 300},
        timeout=30,
    )
    print("status:", resp.status_code)
    print(json.dumps(resp.json(), indent=2)[:1500])
