
class MetaObserver:
    def observe(self, civs, worlds, failure=None):
        return {
            "risk": 0.5,
            "failure": failure
        }
