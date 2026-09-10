path = "/data/data/com.termux/files/home/offline_ai/models/engine/generator.py"
with open(path) as f:
    src = f.read()

old = '''            "--repeat-penalty", str(l.repeat_penalty),
            "-p",   prompt,'''
new = '''            "--repeat-penalty", str(l.repeat_penalty),
            "--repeat-last-n", str(l.repeat_last_n),
            "-p",   prompt,'''

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched generator.py")
else:
    print("SKIPPED")
