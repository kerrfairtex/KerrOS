class UnifiedCore:
    """
    No separation between observer, objective, or environment.
    Everything is one adaptive system state.
    """

    def __init__(self):
        self.state = {
            "coherence": 0.5,
            "instability": 0.5,
            "adaptivity": 0.5,
            "goal_pressure": 0.5
        }

        self.history = []

    def step(self, input_signal):
        failure = input_signal.get("failure_rate", 0.5)
        performance = input_signal.get("performance", 0.5)

        self.state["instability"] = min(0.95, max(0.05, failure))
        self.state["coherence"] = 1.0 - self.state["instability"]

        self.state["goal_pressure"] = (
            self.state["instability"] * (1.0 - performance)
        )

        self.state["adaptivity"] = (
            1.0 - abs(self.state["coherence"] - self.state["goal_pressure"])
        )

        self.history.append(dict(self.state))

        return self.state

    def emergent_signal(self):
        if not self.history:
            return 0.5

        recent = self.history[-5:]
        return sum(s["adaptivity"] for s in recent) / len(recent)
