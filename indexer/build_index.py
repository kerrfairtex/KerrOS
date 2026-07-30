#!/usr/bin/env python3
"""Rebuild KerrOS workspace code index (ADR-052).

Usage:
  python3 indexer/build_index.py
  KERROS_CODE_INDEX=1 python3 indexer/build_index.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("KERROS_CODE_INDEX", "1")

from adapters.code_index.code_index_adapter import CodeIndexAdapter  # noqa: E402


def main() -> int:
    idx = CodeIndexAdapter({"code_index_enabled": True}, workspace=ROOT)
    out = idx.build()
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
