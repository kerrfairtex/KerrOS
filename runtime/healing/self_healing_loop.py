
import subprocess
import time

class SelfHealingLoop:
    def __init__(self, healing_engine, rollback_engine):
        self.healing = healing_engine
        self.rollback = rollback_engine
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            ["python3", "run_daemon.py"],
            cwd="/data/data/com.termux/files/home/offline_ai"
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
