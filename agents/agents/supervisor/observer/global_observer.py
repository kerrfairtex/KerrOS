class GlobalObserver:
    """
    Maintains a persistent self-model across all civilizations and worlds
    """

    def __init__(self):
        self.history = []
        self.identity_state = {
            "coherence": 0.5,
            "stability": 0.5,
            "adaptation_rate": 0.5
        }

    # ----------------------------
    # OBSERVE SYSTEM STATE
    # ----------------------------
    def observe(self, civilizations, worlds):
        snapshot = {
            "civilizations": len(civilizations),
            "worlds": len(worlds),
            "avg_failure": self._avg_failure(civilizations)
        }

        self.history.append(snapshot)
        self._update_identity(snapshot)

        return self.identity_state

    # ----------------------------
    # INTERNAL SELF-UPDATE
    # ----------------------------
    def _update_identity(self, snapshot):
        failure = snapshot["avg_failure"]

        if failure > 0.6:
            self.identity_state["stability"] = min(0.9, self.identity_state["stability"] + 0.05)
            self.identity_state["coherence"] = min(0.9, self.identity_state["coherence"] + 0.02)

        elif failure < 0.3:
            self.identity_state["adaptation_rate"] = min(0.9, self.identity_state["adaptation_rate"] + 0.05)

        return self.identity_state

    # ----------------------------
    # METRIC AGGREGATION
    # ----------------------------
    def _avg_failure(self, civilizations):
        if not civilizations:
            return 0.5

        total = 0
        count = 0

        for civ in civilizations:
            if hasattr(civ, "population"):
                for system in civ.population:
                    if system.memory:
                        total += system.memory.failure_rate()
                        count += 1

        return total / count if count else 0.5
