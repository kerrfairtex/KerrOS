path = "/data/data/com.termux/files/home/offline_ai/core/adaptive_engine.py"
with open(path) as f:
    src = f.read()

old = "            max_tokens=1024"
new = "            max_tokens=4096  # online models handle long answers natively, no RAM ceiling like offline"

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched.")
else:
    print("SKIPPED")
