
from runtime.state.snapshot_engine import SnapshotEngine
from runtime.logs.crash_logger import CrashLogger
from runtime.watchdog.watchdog import Watchdog
from runtime.meta.meta_observer import MetaObserver
from runtime.meta.architecture_feedback import ArchitectureFeedback

class DaemonBoot:
    def __init__(self):
        self.snapshot = SnapshotEngine()
        self.crash = CrashLogger()
        self.watchdog = Watchdog()
        self.meta = MetaObserver()
        self.feedback = ArchitectureFeedback()

    def start(self):
        print("🚀 STARTING PERSISTENT SUPERVISOR DAEMON")

        try:
            self.watchdog.run()
        except Exception as e:
            self.crash.log(e)
            print("⚠ SYSTEM CRASH LOGGED")
