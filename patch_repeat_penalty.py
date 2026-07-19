import json
path = "/data/data/com.termux/files/home/offline_ai/config.json"
with open(path) as f:
    c = json.load(f)

c["repeat_penalty"] = 1.3
c["repeat_last_n"] = 256

with open(path, "w") as f:
    json.dump(c, f, indent=2)

print("Updated repeat_penalty=1.3, repeat_last_n=256")
