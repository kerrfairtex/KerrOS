#!/usr/bin/env python3
"""
scripts/mirror_worm_segment.py
==============================
Mirror a sealed WORM segment via Object Lock adapter (ADR-022).

Usage:
  python3 scripts/mirror_worm_segment.py --segment 1
  python3 scripts/mirror_worm_segment.py --jsonl path.jsonl --manifest path.manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.audit.object_lock import ObjectLockError, mirror_sealed_segment
from adapters.audit.worm_store import WormStore
from kernel.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mirror a sealed WORM segment (ADR-022 Object Lock)"
    )
    parser.add_argument("--segment", type=int, default=None, help="Segment number")
    parser.add_argument("--jsonl", default=None, help="Path to sealed JSONL")
    parser.add_argument("--manifest", default=None, help="Path to sealed manifest")
    parser.add_argument(
        "--worm-dir",
        default=None,
        help="WORM root (default: config audit_retention.worm_dir)",
    )
    args = parser.parse_args(argv)

    cfg = load_config()
    values = dict(cfg.values)

    jsonl: Path | None = None
    manifest: Path | None = None
    if args.jsonl and args.manifest:
        jsonl = Path(args.jsonl)
        manifest = Path(args.manifest)
    elif args.segment is not None:
        worm_dir = args.worm_dir
        if worm_dir is None:
            retention = dict(values.get("audit_retention") or {})
            worm_dir = str(retention.get("worm_dir") or "data/audit_worm")
        worm_path = Path(worm_dir)
        if not worm_path.is_absolute():
            worm_path = cfg.base / worm_path
        store = WormStore(worm_path)
        jsonl, manifest = store.segment_paths(int(args.segment))
    else:
        parser.error("provide --segment N or both --jsonl and --manifest")

    try:
        result = mirror_sealed_segment(
            jsonl, manifest, cfg=values, base=cfg.base
        )
    except ObjectLockError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
