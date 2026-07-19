class UnifiedSupervisorCore:
    def __init__(self, executive, intelligence):
        self.executive = executive
        self.intelligence = intelligence
        self.workers = []

    def route(self, task):
        try:
            if hasattr(self.executive, "decide"):
                return self.executive.decide(task)

            if hasattr(self.intelligence, "infer"):
                return self.intelligence.infer(task)

        except Exception as e:
            return {"error": str(e)}

        return None

    def register_worker(self, cmd):
        p = subprocess.Popen(cmd)
        self.workers.append(p)
        return p

    def monitor_workers(self):
        alive = []
        for p in self.workers:
            if p.poll() is None:
                alive.append(p)
        self.workers = alive
