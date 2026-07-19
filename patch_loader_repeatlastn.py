path = "/data/data/com.termux/files/home/offline_ai/models/engine/loader.py"
with open(path) as f:
    src = f.read()

old = '''        self.repeat_penalty: float = _resolve_float(
            "REPEAT_PENALTY", "repeat_penalty", 1.1
        )'''
new = '''        self.repeat_penalty: float = _resolve_float(
            "REPEAT_PENALTY", "repeat_penalty", 1.1
        )
        self.repeat_last_n: int = _resolve_int(
            "REPEAT_LAST_N", "repeat_last_n", 64
        )'''

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched loader.py")
else:
    print("SKIPPED")
