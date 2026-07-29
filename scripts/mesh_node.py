#!/usr/bin/env python3
"""
scripts/mesh_node.py
====================
Docker / headless event-mesh node entrypoint (C-17).

Boots the KerrOS kernel with event mesh enabled, serves HTTP ingest, and
keeps the process alive. Used by deploy/event_mesh/docker-compose.yml.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

# Ensure repo root is importable when run as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    # Sensible defaults for container runs (compose may override).
    os.environ.setdefault("KERROS_BASE", str(ROOT))
    os.environ.setdefault("KERROS_EVENT_MESH", "1")
    os.environ.setdefault("KERROS_EVENT_MESH_TRANSPORT", "http")
    os.environ.setdefault("KERROS_EVENT_MESH_LISTEN", "0.0.0.0:8787")
    os.environ.setdefault("KERROS_NODE_ID", "mesh-node")

    from kernel.boot import boot, shutdown
    from kernel.contract import SERVICE_EVENT_MESH

    kernel = boot(register_defaults=False)
    mesh = None
    try:
        if kernel.container.has(SERVICE_EVENT_MESH):
            mesh = kernel.container.resolve(SERVICE_EVENT_MESH)
    except Exception:
        mesh = None

    if mesh is None or mesh.http_server is None:
        print(
            "error: event mesh HTTP listener not started — "
            "set KERROS_EVENT_MESH=1, TRANSPORT=http, LISTEN=0.0.0.0:8787",
            file=sys.stderr,
        )
        shutdown()
        return 1

    stop = {"flag": False}

    def _handle(signum: int, frame: object) -> None:
        _ = signum, frame
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    print(
        f"mesh-node ready node_id={mesh.node_id} "
        f"listen={mesh.http_server.host}:{mesh.http_server.port} "
        f"health={mesh.http_server.url_health}",
        flush=True,
    )

    while not stop["flag"]:
        time.sleep(0.5)

    shutdown()
    print("mesh-node stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
