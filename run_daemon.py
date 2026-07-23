#!/usr/bin/env python3
"""
run_daemon.py
=============
KerrOS daemon entry point (KOS-011).

Run directly for a single session, or under the kernel watchdog:
    python3 run_daemon.py
    python3 -m kernel.watchdog_cli run_daemon.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    if "--watchdog" in sys.argv:
        from kernel.watchdog import supervise
        supervise([sys.executable, __file__])
        return 0

    from kernel.boot import boot
    from kernel.decision_log import record_decision

    kernel = boot()
    record_decision(
        actor="daemon",
        decision_type="daemon",
        input_summary="run_daemon.start",
        outcome="started",
        reason=f"phase={kernel.phase.value}",
    )

    print(f"[daemon] KerrOS ready — workspace={kernel.config.workspace}")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        record_decision(
            actor="daemon",
            decision_type="daemon",
            input_summary="run_daemon.stop",
            outcome="stopped",
            reason="keyboard interrupt",
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
