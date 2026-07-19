
class SupervisorEvolutionCore:
    def __init__(self, learner, mutation_engine, rewrite_core, logger):
        self.learner = learner
        self.mutation = mutation_engine
        self.rewrite = rewrite_core
        self.logger = logger

    def step(self, meta_signal):
        risk = meta_signal.get("risk_level", 0.0)

        if risk > 0.8:
            signal = "RESTRUCTURE_CORE"
        elif risk > 0.6:
            signal = "ENABLE_SAFE_MODE"
        elif risk < 0.3:
            signal = "OPTIMIZE_PERFORMANCE"
        else:
            signal = "NO_CHANGE"

        action = self.rewrite.evaluate_and_rewrite(signal)

        self.logger.log({
            "signal": signal,
            "action": action,
            "risk": risk
        })

        return action
