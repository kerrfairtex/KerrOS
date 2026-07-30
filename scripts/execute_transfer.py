#!/usr/bin/env python3
"""Execute a transfer intent via local_copy / http_put pipeline (ADR-027)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.audit.transfer_pipeline import execute_transfer
from kernel.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute transfer intent (ADR-027)")
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--token", default=None)
    parser.add_argument(
        "--segments",
        default="",
        help="Optional comma-separated sealed segment numbers",
    )
    args = parser.parse_args(argv)

    segs = [int(x) for x in args.segments.split(",") if x.strip().isdigit()]
    cfg = load_config()
    out = execute_transfer(
        args.id,
        cfg=cfg.values,
        base=cfg.base,
        segment_ids=segs or None,
        audit_token=args.token,
    )
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
