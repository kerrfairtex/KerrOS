
class AutoPatcher:
    def patch(self, obj, missing):
        for m in missing:
            if m == "bind_supervisor":
                def fn(supervisor):
                    obj.supervisor = supervisor
                    return obj
                setattr(obj, m, fn)

            elif m == "run":
                def fn():
                    print("fallback watchdog run")
                setattr(obj, m, fn)

        return obj
