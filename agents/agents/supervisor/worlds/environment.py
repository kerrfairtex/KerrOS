class Environment:
    """
    Defines a rule-set (physics) for evaluating systems
    """

    def __init__(self, name, instability=0.5, noise=0.1):
        self.name = name
        self.instability = instability
        self.noise = noise

    def perturb_score(self, base_score):
        import random
        drift = (random.random() - 0.5) * self.noise
        return max(0.0, min(1.0, base_score + drift * self.instability))
