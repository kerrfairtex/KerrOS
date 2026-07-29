#!/usr/bin/env python3
"""
scripts/migrate_sqlite_rag_to_qdrant.py
=======================================
Copy KerrOS SQLite RAG chunks into the optional Qdrant collection (C-18).

SQLite FTS remains the primary store — this only backfills vectors for hybrid
recall. Respects MEMORY_SEPARATION (kerros_memory / non-OmniRoute collections).

Usage:
  KERROS_QDRANT_ENABLED=1 python3 scripts/migrate_sqlite_rag_to_qdrant.py --dry-run
  KERROS_QDRANT_ENABLED=1 python3 scripts/migrate_sqlite_rag_to_qdrant.py --batch-size 64
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count/list only")
    parser.add_argument("--limit", type=int, default=None, help="Max chunks")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N")
    parser.add_argument("--source", type=str, default=None, help="Filter by source")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Force KERROS_QDRANT_ENABLED=1 for this process",
    )
    args = parser.parse_args(argv)

    if args.enable:
        os.environ["KERROS_QDRANT_ENABLED"] = "1"

    from rag import store as rag_store
    from adapters.memory.qdrant_vector_store import QdrantVectorStore
    from kernel.config import load_config

    total = rag_store.count_chunks(source=args.source)
    print(f"sqlite chunks: {total}" + (f" (source={args.source})" if args.source else ""))

    rows = list(
        rag_store.iter_chunks(
            source=args.source, limit=args.limit, offset=args.offset
        )
    )
    print(f"selected: {len(rows)} (offset={args.offset}, limit={args.limit})")

    if args.dry_run:
        for row_id, text, source, category in rows[:10]:
            preview = text.replace("\n", " ")[:80]
            print(f"  id={row_id} source={source} cat={category} text={preview!r}")
        if len(rows) > 10:
            print(f"  … {len(rows) - 10} more")
        return 0

    cfg = load_config().values
    store = QdrantVectorStore(cfg)
    if not store.enabled:
        print(
            "error: Qdrant disabled — set KERROS_QDRANT_ENABLED=1 or pass --enable",
            file=sys.stderr,
        )
        return 2

    batch_size = max(1, int(args.batch_size))
    ok_batches = 0
    fail_batches = 0
    upserted = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        # Group batch by source for payload consistency within each upsert call.
        by_source: dict[str, list[tuple[int, str, str]]] = {}
        for row_id, text, source, category in batch:
            by_source.setdefault(source, []).append((row_id, text, category))

        batch_ok = True
        for source, items in by_source.items():
            texts = [t for _id, t, _cat in items]
            indices = [int(_id) for _id, _t, _cat in items]
            # Prefer first category; per-chunk category is in sqlite but payload
            # is shared — attach sqlite_ids list for traceability.
            meta = {
                "category": items[0][2],
                "sqlite_ids": indices,
            }
            if not store.upsert(
                texts, source=source, metadata=meta, indices=indices
            ):
                batch_ok = False
                print(
                    f"upsert failed source={source}: {store.last_error}",
                    file=sys.stderr,
                )
                break
        if batch_ok:
            ok_batches += 1
            upserted += len(batch)
        else:
            fail_batches += 1

    print(
        f"done upserted={upserted} ok_batches={ok_batches} "
        f"fail_batches={fail_batches} collection={store.collection} url={store.url}"
    )
    return 0 if fail_batches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
