path = "/data/data/com.termux/files/home/offline_ai/cli/chat.py"
with open(path) as f:
    src = f.read()

old = '''                ("/react <task>",      "ReAct agent — multi-step reasoning"),'''
new = '''                ("/react <task>",      "ReAct agent — multi-step reasoning"),
                ("/knowledge <q>",     "Knowledge Agent — RAG-grounded Q&A + live tools"),'''

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched help.")
else:
    print("SKIPPED")
