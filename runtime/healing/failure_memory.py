
import time
from collections import defaultdict

class FailureMemory:
    def __init__(self):
        self.failures = []
        self.counts = defaultdict(int)

    def record(self, error_type):
        self.failures.append({
            "time": time.time(),
            "error": error_type
        })
        self.counts[error_type] += 1

    def repeated(self, error_type, threshold=3):
        return self.counts[error_type] >= threshold
