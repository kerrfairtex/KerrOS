
import subprocess
import time
import os
from core.config import BASE

class PersistentDaemon:
    def __init__(self):
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            ["python3", "run_daemon.py"],
            cwd=str(BASE)
        )

    def run(self):
        self.start()

        while True:
            if self.process.poll() is not None:
                print("💥 CRASH DETECTED → RESTARTING")
                self.start()
            time.sleep(2)
