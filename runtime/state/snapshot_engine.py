
import json, time, os

class SnapshotEngine:
    def __init__(self, path="runtime/state/snapshot.json"):
        self.path = os.path.expanduser("~/offline_ai/" + path)

    def save(self, state):
        state["timestamp"] = time.time()
        with open(self.path, "w") as f:
            json.dump(state, f, indent=2)

    def load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as f:
            return json.load(f)
