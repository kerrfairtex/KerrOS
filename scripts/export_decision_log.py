#!/usr/bin/env python3
"""
scripts/export_decision_log.py
==============================
Export KerrOS decision_log to JSONL (ADR-017).

Usage:
  python3 scripts/export_decision_log.py
  python3 scripts/export_decision_log.py -o /tmp/audit.jsonl
  python3 scripts/export_decision_log.py --since-id 100 --db data/decision_log.db
  python3 scripts/export_decision_log.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.audit.decision_log_export import export_decision_log_jsonl
from kernel.decision_log import DecisionLog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export decision_log to JSONL")
    parser.add_argument(
        "-o",
        "--output",
        default=str(ROOT / "data" / "audit_export" / "decision_log.jsonl"),
        help="Output JSONL path",
    )
    parser.add_argument("--db", default=None, help="Path to decision_log.db")
    parser.add_argument("--since-id", type=int, default=0)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify the hash chain; do not write a file",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip chain verify before export (not recommended)",
    )
    args = parser.parse_args(argv)

    log = DecisionLog(args.db) if args.db else DecisionLog()
    if args.verify_only:
        result = log.verify_chain()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1

    out = export_decision_log_jsonl(
        args.output,
        log=log,
        since_id=args.since_id,
        verify_before_export=not args.no_verify,
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
