
class ArchitectureFeedback:
    def generate_signal(self, meta):
        r = meta.get("risk", 0.0)

        if r > 0.8:
            return "RESTRUCTURE"
        if r > 0.6:
            return "SAFE_MODE"
        return "STABLE"
