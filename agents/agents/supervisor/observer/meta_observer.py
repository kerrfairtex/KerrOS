class MetaObserver:
    """
    Collapses observer + system + objective into a single adaptive loop
    """

    def __init__(self, global_observer, objective_model=None):
        self.global_observer = global_observer
        self.objective_model = objective_model
        self.collapse_state = {
            "unity": 0.5,
            "feedback_intensity": 0.5,
            "self_reference_depth": 0.5
        }

    # ----------------------------
    # META OBSERVATION LOOP
    # ----------------------------
    def tick(self, civilizations, worlds, systems):
        identity = self.global_observer.observe(civilizations, worlds)

        avg_failure = identity.get("stability", 0.5)

        # collapse dynamics: observer influences objective + vice versa
        if self.objective_model:
            self.objective_model.adapt({
                "failure_rate": avg_failure
            })

        self._update_collapse(identity)

        return {
            "identity": identity,
            "collapse": self.collapse_state
        }

    # ----------------------------
    # SELF-REFERENCE COLLAPSE DYNAMICS
    # ----------------------------
    def _update_collapse(self, identity):
        stability = identity.get("stability", 0.5)
        coherence = identity.get("coherence", 0.5)

        # system becomes more unified when stable
        if stability > 0.7:
            self.collapse_state["unity"] = min(0.95, self.collapse_state["unity"] + 0.03)

        # system becomes more self-referential when unstable
        if stability < 0.4:
            self.collapse_state["self_reference_depth"] = min(
                0.95,
                self.collapse_state["self_reference_depth"] + 0.04
            )

        # coherence stabilizes feedback loop
        self.collapse_state["feedback_intensity"] = min(
            0.95,
            max(0.1, coherence)
        )

        return self.collapse_state
