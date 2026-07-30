#!/usr/bin/env python3
"""Record a sealed-cold erasure review (ADR-026). Never rewrites WORM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.audit.erasure_ledger import REVIEW_OUTCOMES, review_sealed_erasure
from kernel.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review sealed-cold erasure (ADR-026)")
    parser.add_argument("--id", type=int, required=True, help="Parent erasure request id")
    parser.add_argument(
        "--outcome",
        required=True,
        choices=list(REVIEW_OUTCOMES),
    )
    parser.add_argument("--notes", default="")
    parser.add_argument("--actor", default="cli")
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)

    cfg = load_config()
    out = review_sealed_erasure(
        args.id,
        outcome=args.outcome,
        notes=args.notes,
        actor=args.actor,
        cfg=cfg.values,
        base=cfg.base,
        audit_token=args.token,
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
