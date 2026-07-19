
class SelfRewriteCore:
    def __init__(self, mutation_engine, learner):
        self.engine = mutation_engine
        self.learner = learner
        self.change_log = []

    def evaluate_and_rewrite(self, signal):
        proposal = self.engine.propose(signal)

        if proposal == "no_change":
            return "NO_ACTION"

        # SAFE GUARD: only log, do NOT execute code rewriting
        self.change_log.append({
            "time": __import__("time").time(),
            "proposal": proposal,
            "signal": signal
        })

        self.engine.apply(proposal)
        return proposal
