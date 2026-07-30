#!/usr/bin/env python3
"""Record a cross-border transfer intent (ADR-026). Does not move bytes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.audit.transfer_ledger import MECHANISMS, record_transfer_intent
from kernel.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record transfer intent (ADR-026)")
    parser.add_argument("--to", required=True, help="Destination region")
    parser.add_argument("--mechanism", required=True, choices=list(MECHANISMS))
    parser.add_argument("--from-region", default="", dest="from_region")
    parser.add_argument("--subject", default="")
    parser.add_argument("--purpose", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--actor", default="cli")
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)

    cfg = load_config()
    out = record_transfer_intent(
        to_region=args.to,
        mechanism=args.mechanism,
        from_region=args.from_region,
        subject_ref=args.subject,
        purpose=args.purpose,
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
