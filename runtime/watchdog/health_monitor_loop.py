class HealthMonitorLoop:
    """
    Tracks long-term system stability trends.
    """

    def __init__(self):
        self.history = []

    def record(self, failure_type):
        self.history.append(failure_type)

    def stability_score(self):
        if not self.history:
            return 1.0

        critical = self.history.count("memory_overflow")
        errors = len(self.history)

        score = 1.0 - (critical * 0.2 + errors * 0.05)
        return max(0.0, min(1.0, score))
