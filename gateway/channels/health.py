"""
gateway/channels/health.py
==========================
Soft channel health probes (ADR-104).

Reports enabled/live/running/inbox depth and Soft latency for each adapter
plus gateway/discord gateway/status.
"""

from __future__ import annotations

import time
from typing import Any


def probe_channels() -> dict[str, Any]:
    from gateway.channels.discord_gateway import get_discord_gateway
    from gateway.channels.registry import list_channels
    from gateway.channels.siem_queue import queue_status
    from gateway.channels.trace import read_trace

    t0 = time.time()
    channels = list_channels()
    probes = []
    for c in channels:
        probes.append(
            {
                "channel": c.get("channel"),
                "ok": bool(c.get("ok", True)),
                "enabled": c.get("enabled"),
                "live": c.get("live"),
                "running": c.get("running"),
                "mode": c.get("mode"),
                "soft_inbox": c.get("soft_inbox"),
                "soft_outbox": c.get("soft_outbox"),
            }
        )
    gw = get_discord_gateway().status()
    siem = queue_status()
    traces = len(read_trace(limit=5))
    return {
        "ok": True,
        "latency_ms": int((time.time() - t0) * 1000),
        "channels": probes,
        "discord_gateway": {
            "running": gw.get("running"),
            "mode": gw.get("mode"),
            "live_error": gw.get("live_error"),
        },
        "siem_queue_pending": siem.get("pending"),
        "trace_sample": traces,
    }
