import time

class Watchdog:
    def __init__(self, supervisor):
        self.supervisor = supervisor

    def run(self):
        while True:
            try:
                self.supervisor.monitor_workers()
            except Exception:
                pass
            time.sleep(2)
