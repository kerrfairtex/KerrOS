#!/usr/bin/env python3
"""Loads .env + api_config.yaml and reports which integrations are configured.

Never prints secret values — only env *names* and OK/MISSING status.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))

sys.path.insert(0, BASE)

from adapters.integrations.registry import (  # noqa: E402
    catalog_status,
    format_status_lines,
    list_tiers,
    resolve_tier,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="KerrOS integration status (ADR-055)")
    parser.add_argument(
        "section",
        nargs="?",
        help="Optional section filter (e.g. llm_cloud, coding_agents, coding)",
    )
    parser.add_argument("--ready", action="store_true", help="Only show configured rows")
    parser.add_argument("--tier", metavar="NAME", help="Resolve routing tier (sol|terra|luna|coding|research)")
    args = parser.parse_args()

    if args.tier:
        hit = resolve_tier(args.tier)
        print(hit)
        return 0 if hit.get("ok") else 1

    section = args.section
    # Allow shorthand: / coding → routing tier info + coding_agents section
    if section in ("sol", "terra", "luna", "coding", "research"):
        tiers = list_tiers()
        spec = tiers.get(section) or {}
        print(f"[tier:{section}] {spec.get('description', '')}")
        print(f"  providers: {', '.join(spec.get('providers') or [])}")
        print(resolve_tier(section))
        if section == "coding":
            section = "coding_agents"
        else:
            return 0

    st = catalog_status(sections=[section] if section else None)
    for line in format_status_lines(st, section=section, ready_only=args.ready):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
