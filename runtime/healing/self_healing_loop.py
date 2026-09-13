"""
Self-healing loop daemon launcher for KerrOS.
"""
import subprocess
import sys
import time
from pathlib import Path


class SelfHealingLoop:
    def __init__(self, healing_engine, rollback_engine):
        self.healing = healing_engine
        self.rollback = rollback_engine
        self.process = None

    def start(self):
        from core.config import BASE

        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "run_daemon.py")],
            cwd=str(BASE),
        )

    def run(self):
        self.start()

        while True:
            if self.process.poll() is not None:
                result = self.healing.evaluate("process_crash")

                if result == "SAFE_MODE":
                    print("🧯 SAFE MODE ACTIVATED")
                    self.rollback.rollback()
                    time.sleep(5)
                else:
                    print("🔁 RESTARTING NORMAL MODE")
                    self.start()

            time.sleep(self.healing.delay())
