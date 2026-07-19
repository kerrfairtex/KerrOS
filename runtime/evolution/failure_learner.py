
class FailureLearner:
    def __init__(self):
        self.history = []

    def observe(self, failure_event):
        self.history.append({
            "time": __import__("time").time(),
            "event": failure_event
        })

    def pattern_strength(self):
        return len(self.history)
