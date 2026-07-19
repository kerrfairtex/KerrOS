
import os

def verify_system():
    required = [
        "runtime/watchdog/watchdog.py",
        "runtime/meta/meta_observer.py"
    ]

    missing = []
    for f in required:
        if not os.path.exists(os.path.expanduser("~/offline_ai/" + f)):
            missing.append(f)

    return missing
