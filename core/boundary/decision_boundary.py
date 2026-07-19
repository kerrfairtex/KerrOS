class DecisionBoundary:
    def __init__(self, executive, intelligence):
        self.executive = executive
        self.intelligence = intelligence

    def route(self, task):
        if hasattr(self.executive, "decide"):
            return self.executive.decide(task)

        if hasattr(self.intelligence, "infer"):
            return self.intelligence.infer(task)

        return None
