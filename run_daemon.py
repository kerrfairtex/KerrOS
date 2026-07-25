#!/usr/bin/env python3
"""
run_daemon.py — legacy entry point; prefer ./kerrd start (Phase 2).
"""
from __future__ import annotations

import sys


def main() -> int:
    if "--watchdog" in sys.argv:
        from kernel.watchdog import supervise
        supervise([sys.executable, "kerrd", "start", "--watchdog"])
        return 0
    from runtime.kerrd import main as kerrd_main
    return kerrd_main(["start"])


if __name__ == "__main__":
    raise SystemExit(main())
