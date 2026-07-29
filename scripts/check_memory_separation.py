#!/usr/bin/env python3
"""Static P5 guard: OmniRoute memory stays separate from KerrOS RAG."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "MEMORY_SEPARATION.md"
COMPOSE = ROOT / "deploy" / "omniroute" / "docker-compose.yml"
CAP = ROOT / "config" / "capabilities" / "omniroute.yaml"
STORE = ROOT / "rag" / "store.py"
GUARD = ROOT / "rag" / "path_guard.py"


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not DOC.is_file():
        _fail(f"missing {DOC}")
    doc = DOC.read_text(encoding="utf-8")
    for needle in (
        "different jobs",
        "rag_store.db",
        "kerros-omniroute-data",
        "kerros_memory",
        "don't merge",
    ):
        if needle not in doc and needle.replace("'", "’") not in doc:
            # allow curly apostrophe variant for don't
            if "dont merge" in doc.replace("'", "").replace("’", "").lower():
                continue
            if needle == "don't merge" and "do not merge" in doc.lower():
                continue
            _fail(f"MEMORY_SEPARATION.md missing '{needle}'")

    if not GUARD.is_file():
        _fail(f"missing {GUARD}")
    if not STORE.is_file():
        _fail(f"missing {STORE}")
    store = STORE.read_text(encoding="utf-8")
    if "path_guard" not in store or "assert_kerros_paths" not in store:
        _fail("rag/store.py must call path_guard.assert_kerros_paths")

    if not COMPOSE.is_file():
        _fail(f"missing {COMPOSE}")
    compose = COMPOSE.read_text(encoding="utf-8")
    if "kerros-omniroute-data" not in compose:
        _fail("compose must use kerros-omniroute-data volume")
    if "rag_store.db" in compose:
        _fail("compose must not reference KerrOS rag_store.db")

    if not CAP.is_file():
        _fail(f"missing {CAP}")
    cap = CAP.read_text(encoding="utf-8")
    if "memory_boundary" not in cap or "separate" not in cap:
        _fail("omniroute.yaml must declare memory_boundary: separate")

    print("OK: OmniRoute / KerrOS memory separation guards passed")
    print(f"  doc:     {DOC.relative_to(ROOT)}")
    print(f"  guard:   {GUARD.relative_to(ROOT)}")
    print(f"  compose: {COMPOSE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
