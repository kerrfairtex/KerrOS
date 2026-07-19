import re

class FailureAnalyzer:
    """
    Converts crash logs into structured failure types.
    """

    def classify(self, log: str):
        if not log:
            return "unknown"

        if "NameError" in log:
            return "code_error"

        if "ImportError" in log:
            return "dependency_error"

        if "MemoryError" in log:
            return "memory_overflow"

        if "timeout" in log.lower():
            return "execution_timeout"

        if "Traceback" in log:
            return "runtime_exception"

        return "unknown"
