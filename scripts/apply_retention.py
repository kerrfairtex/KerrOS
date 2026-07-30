#!/usr/bin/env python3
"""
scripts/apply_retention.py
==========================
Apply decision_log retention policy once (ADR-019). Cron-friendly.

Usage:
  python3 scripts/apply_retention.py
  python3 scripts/apply_retention.py --enable --retain-days 30 --action archive
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.audit.retention import apply_retention, retention_config_from
from kernel.config import load_config
from kernel.decision_log import DecisionLog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply decision_log retention")
    parser.add_argument("--db", default=None)
    parser.add_argument("--enable", action="store_true", help="Force enabled for this run")
    parser.add_argument("--retain-days", type=int, default=None)
    parser.add_argument("--action", choices=("archive", "purge"), default=None)
    parser.add_argument("--worm-dir", default=None)
    parser.add_argument("--allow-purge", action="store_true")
    parser.add_argument("--token", default=None, help="Audit RBAC token")
    parser.add_argument(
        "--now",
        type=float,
        default=None,
        help="Override wall clock (unix ts) for tests",
    )
    args = parser.parse_args(argv)

    try:
        kcfg = load_config()
        base = kcfg.base
        values = dict(kcfg.values)
    except Exception:
        base = ROOT
        values = {}

    policy = retention_config_from(values, base=base)
    if args.enable:
        policy["enabled"] = True
    if args.retain_days is not None:
        policy["retain_days"] = args.retain_days
    if args.action:
        policy["action"] = args.action
    if args.worm_dir:
        policy["worm_dir"] = args.worm_dir
    if args.allow_purge:
        policy["allow_purge"] = True

    log = DecisionLog(args.db) if args.db else DecisionLog()
    result = apply_retention(
        log,
        cfg={**values, "audit_retention": policy},
        now=args.now,
        base=base,
        audit_token=args.token,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
