
class ContractRegistry:
    REQUIRED = {
        "ExecutiveBrain": ["bind_supervisor"],
        "Watchdog": ["run", "launch"],
        "MetaObserver": ["observe"]
    }

    def validate(self, obj, cls):
        return [
            m for m in self.REQUIRED.get(cls, [])
            if not hasattr(obj, m)
        ]
