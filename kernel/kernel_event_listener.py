#!/usr/bin/env python3
"""
Kernel event listener for the autonomous supervisor.
Watches kernel_events.log for new lines and dispatches events.
"""

import json
import os
import time
from pathlib import Path

# Absolute paths
BASE_DIR = Path('/data/data/com.termux/files/home/offline_ai')
LOG_PATH = BASE_DIR / "kernel_events.log"

def on_tool_added(path: str):
    """Callback for tool_added event."""
    print(f"[Supervisor] Detected new tool: {path}")
    # Integration point: Trigger capability registry refresh here
    # e.g., self.kernel.capability_registry.load(path)

EVENTS = {
    "tool_added": on_tool_added,
}

class LogWatcher:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        if not log_path.exists():
            log_path.touch()
        self._position = log_path.stat().st_size

    def poll(self):
        """Yield new lines added since last poll."""
        if self.log_path.stat().st_size < self._position:
            # File was truncated/rotated
            self._position = 0
            
        with self.log_path.open("r", encoding="utf-8") as f:
            f.seek(self._position)
            lines = f.readlines()
            self._position = f.tell()
            for line in lines:
                yield line.rstrip("\n")

def run_listener():
    watcher = LogWatcher(LOG_PATH)
    print(f"[Listener] Monitoring {LOG_PATH}...")

    try:
        while True:
            for raw in watcher.poll():
                try:
                    msg = json.loads(raw)
                    event = msg.get("event")
                    payload = msg.get("payload")
                    if event in EVENTS:
                        EVENTS[event](payload)
                    else:
                        print(f"[Listener] Unknown event: {event}")
                except json.JSONDecodeError:
                    print(f"[Listener] Bad JSON line: {raw}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("[Listener] Shutting down.")

if __name__ == "__main__":
    run_listener()
