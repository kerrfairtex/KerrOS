path = "/data/data/com.termux/files/home/offline_ai/core/complete.py"
with open(path) as f:
    src = f.read()

old = "MAX_CONTINUATIONS = 4  # hard safety cap — prevents infinite loops on a stuck model"
new = "MAX_CONTINUATIONS = 1  # small model reliability drops sharply after 1 continuation; cap here rather than risk repeated restarts"

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched.")
else:
    print("SKIPPED")
