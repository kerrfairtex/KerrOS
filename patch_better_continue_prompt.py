path = "/data/data/com.termux/files/home/offline_ai/core/complete.py"
with open(path) as f:
    src = f.read()

old = '''        current_user_message = "Continue exactly where you left off. Do not repeat anything already said."'''
new = '''        last_words = " ".join(full_response.strip().split()[-8:])
        current_user_message = (
            f"Your previous answer was cut off. It ended with: \\"...{last_words}\\"\\n"
            f"Continue writing the NEXT part only. Do NOT repeat the sentence above. "
            f"Do NOT restart the explanation. Just continue directly from that point."
        )'''

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched.")
else:
    print("SKIPPED")
