
from runtime.watchdog.watchdog import Watchdog
from runtime.meta.meta_observer import MetaObserver
from runtime.meta.architecture_feedback import ArchitectureFeedback

class Bootstrap:
    def __init__(self):
        self.watchdog = Watchdog()
        self.meta = MetaObserver()
        self.feedback = ArchitectureFeedback()

    def start(self):
        print("BOOTING SUPERVISOR KERNEL")
        self.watchdog.run()
