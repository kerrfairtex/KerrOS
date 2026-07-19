path = "/data/data/com.termux/files/home/offline_ai/core/multi_api.py"
with open(path) as f:
    src = f.read()

old = '''    if any(k in lower for k in ["research","history of","explain in detail",
            "deep dive","full explanation","compare","analyze","what is the"]):
        return "research"'''
new = '''    if any(k in lower for k in ["research","history of","explain in detail",
            "deep dive","full explanation","compare","analyze","what is the",
            "complete answer","comprehensive","in depth","thorough"]):
        return "research"'''

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched task detection.")
else:
    print("SKIPPED")
