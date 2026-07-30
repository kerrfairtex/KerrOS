#!/usr/bin/env python3
"""
scripts/record_erasure_request.py
=================================
Record a lawful erasure request (ADR-025). Does not rewrite WORM.

Usage:
  python3 scripts/record_erasure_request.py --subject hash:abc --ids 1,2,3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.audit.erasure_ledger import evaluate_erasure_request
from kernel.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record erasure request (ADR-025)")
    parser.add_argument("--subject", required=True, help="Subject reference (prefer hash)")
    parser.add_argument("--ids", default="", help="Comma-separated decision ids")
    parser.add_argument("--basis", default="", help="Legal basis note")
    parser.add_argument("--notes", default="")
    parser.add_argument("--actor", default="cli")
    parser.add_argument("--token", default=None)
    args = parser.parse_args(argv)

    ids = [int(x) for x in args.ids.split(",") if x.strip().isdigit()]
    cfg = load_config()
    out = evaluate_erasure_request(
        subject_ref=args.subject,
        decision_ids=ids,
        legal_basis=args.basis,
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
