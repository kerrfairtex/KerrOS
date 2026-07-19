
import time

class HealingEngine:
    def __init__(self, failure_memory):
        self.memory = failure_memory
        self.safe_mode = False

    def evaluate(self, error):
        self.memory.record(error)

        if self.memory.repeated(error):
            self.safe_mode = True
            return "SAFE_MODE"

        return "RESTART"

    def delay(self):
        if self.safe_mode:
            return 5
        return 2
