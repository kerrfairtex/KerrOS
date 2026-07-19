
import os
import json

class RollbackEngine:
    def __init__(self, path="runtime/state/snapshot.json"):
        self.path = os.path.expanduser("~/offline_ai/" + path)

    def load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as f:
            return json.load(f)

    def rollback(self):
        state = self.load()
        print("↩️ Rolling back to last stable state")
        return state
