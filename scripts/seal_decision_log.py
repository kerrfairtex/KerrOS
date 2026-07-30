#!/usr/bin/env python3
"""
scripts/seal_decision_log.py
============================
Seal a decision_log id prefix into a software-WORM JSONL segment (ADR-019).

Usage:
  python3 scripts/seal_decision_log.py --through-id 100
  python3 scripts/seal_decision_log.py --through-id 100 --worm-dir /tmp/worm
  python3 scripts/seal_decision_log.py --verify 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.audit.rbac import AuditRbacError
from adapters.audit.worm_store import WormStore, WormStoreError
from kernel.decision_log import DecisionLog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal decision_log to WORM segment")
    parser.add_argument("--db", default=None, help="Path to decision_log.db")
    parser.add_argument(
        "--worm-dir",
        default=str(ROOT / "data" / "audit_worm"),
        help="WORM root directory",
    )
    parser.add_argument("--through-id", type=int, default=None)
    parser.add_argument("--token", default=None, help="Audit RBAC token")
    parser.add_argument(
        "--verify",
        type=int,
        default=None,
        metavar="N",
        help="Verify sealed segment N and exit",
    )
    parser.add_argument("--list", action="store_true", help="List sealed segments")
    args = parser.parse_args(argv)

    store = WormStore(args.worm_dir)
    if args.list:
        print(json.dumps(store.list_segments(), indent=2, sort_keys=True))
        return 0
    if args.verify is not None:
        result = store.verify_segment(args.verify)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.through_id is None:
        parser.error("--through-id is required (or use --list / --verify)")

    log = DecisionLog(args.db) if args.db else DecisionLog()
    try:
        out = store.seal_from_log(
            log, through_id=args.through_id, audit_token=args.token
        )
    except (WormStoreError, AuditRbacError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
