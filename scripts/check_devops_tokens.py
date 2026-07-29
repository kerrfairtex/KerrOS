#!/usr/bin/env python3
"""Audit DevOps deploy credentials for least-privilege shape/presence."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from tools.devops_tokens import SERVICE_SPECS, audit_all, summary_table


def main() -> int:
    checks = audit_all()
    print(summary_table(checks))
    print()
    failed = [c for c in checks if not c.ok]
    for c in checks:
        if c.warnings:
            print(f"warn[{c.service}]: " + "; ".join(c.warnings))
    if failed:
        print(f"\n{len(failed)} service(s) failed credential checks "
              f"(of {len(SERVICE_SPECS)}). See docs/DEVOPS_TOKEN_SCOPING.md")
        return 1
    print(f"\nAll {len(SERVICE_SPECS)} services OK (or optional+absent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
