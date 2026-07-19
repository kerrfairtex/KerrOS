
import json, time, os

class EvolutionLogger:
    def __init__(self, path="runtime/evolution/log.jsonl"):
        self.path = os.path.expanduser("~/offline_ai/" + path)

    def log(self, event):
        entry = {
            "time": time.time(),
            "event": event
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
