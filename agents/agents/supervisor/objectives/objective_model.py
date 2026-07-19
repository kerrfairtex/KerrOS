class ObjectiveModel:
    """
    Learns and mutates what 'success' means
    """

    def __init__(self):
        self.weights = {
            "stability": 0.5,
            "performance": 0.5
        }

    def evaluate(self, metrics):
        return (
            metrics.get("stability", 0.5) * self.weights["stability"] +
            metrics.get("performance", 0.5) * self.weights["performance"]
        )

    def adapt(self, feedback):
        """
        Adjust objective weights based on system outcomes
        """

        if feedback.get("failure_rate", 0.5) > 0.6:
            self.weights["stability"] = min(0.9, self.weights["stability"] + 0.05)
            self.weights["performance"] = max(0.1, self.weights["performance"] - 0.05)

        elif feedback.get("failure_rate", 0.5) < 0.3:
            self.weights["performance"] = min(0.9, self.weights["performance"] + 0.05)
            self.weights["stability"] = max(0.1, self.weights["stability"] - 0.05)

        return self.weights
